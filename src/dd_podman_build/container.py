import json
import os
import subprocess
from datetime import datetime
from typing_extensions import Annotated

import typer

app = typer.Typer()


def parse_docker_metadata(tags: list[str], labels: list[str]):
    with open(os.environ["DOCKER_METADATA_OUTPUT_JSON"]) as metadata_in:
        metadata = json.load(metadata_in)

    if not isinstance(metadata, dict):
        raise Exception("Malformed DOCKER_METADATA_OUTPUT_JSON: top-level not a dict")

    if "tags" in metadata:
        if not isinstance(metadata["tags"], list):
            raise Exception("Malformed DOCKER_METADATA_OUTPUT_JSON: tags not a list")

        for metadata_tag in map(str, metadata["tags"]):
            if metadata_tag not in tags:
                tags.append(metadata_tag)

    if "labels" in metadata:
        if not isinstance(metadata["labels"], list):
            raise Exception("Malformed DOCKER_METADATA_OUTPUT_JSON: labels not a list")

        for metadata_label in map(str, metadata["labels"]):
            if metadata_label not in tags:
                labels.append(metadata_label)


def do_rechunk(tmp_tag: str, base_tag: str, rechunk_image: str | None) -> str:
    rechunk_image = rechunk_image or os.environ.get(
        "RECHUNK_IMAGE", "quay.io/centos-bootc/centos-bootc:stream9"
    )
    rechunk_tag = f"localhost/{base_tag}:tmp-{datetime.now().strftime('%y%m%d%H%M%S')}"

    _ = subprocess.run(
        [
            "podman",
            "run",
            "--rm",
            "--privileged",
            "--security-opt=label=disable",
            "--pull=newer",
            "-v",
            "/var/lib/containers:/var/lib/containers",
            "-v",
            "/var/tmp:/var/tmp",
            rechunk_image,
            "rpm-ostree",
            "compose",
            "build-chunked-oci",
            "--bootc",
            "--format-version=1",
            "--max-layers=99",
            "--from",
            tmp_tag,
            "--output",
            f"containers-storage:{rechunk_tag}",
        ]
    )

    return rechunk_tag


def write_iidfile(tmp_tag: str, iidfile: str):
    inspection = json.loads(
        subprocess.run(
            ["podman", "inspect", tmp_tag],
            stdout=subprocess.PIPE,
            check=True,
            encoding="utf-8",
        ).stdout
    )
    if not isinstance(inspection, list):
        raise Exception("`podman inspect` output is not a list")
    if len(inspection) > 1:
        raise Exception("`podman inspect` returrned more than one image")
    if not isinstance(inspection[0], dict):
        raise Exception("`podman inspect` list doesn't contain a dict")

    image_id = inspection[0].get("Id", None)
    if not isinstance(image_id, str):
        raise Exception("`podman inspect` output missing or malformed image ID")

    with open(iidfile, "w") as iid_out:
        _ = iid_out.write(image_id)


def make_push_argv(private_key: str | None, passphrase_file: str | None) -> list[str]:
    push_argv: list[str] = []

    private_key = private_key or os.environ.get("SIGSTORE_PRIVATE_KEY_FILE", None)
    passphrase_file = passphrase_file or os.environ.get(
        "SIGSTORE_PASSPHRASE_FILE", None
    )

    if private_key and passphrase_file:
        push_argv += [
            "--sign-by-sigstore-private-key",
            private_key,
            "--sign-passphrase-file",
            passphrase_file,
        ]

    return push_argv


@app.command(name="container")
def build_container(
    context: Annotated[
        str, typer.Argument(help="directory containing context to build")
    ] = ".",
    filename: Annotated[
        str | None, typer.Option("-f", "--filename", help="path to Dockerfile")
    ] = None,
    tag: Annotated[str | None, typer.Option(help="tag to use for built image")] = None,
    target: Annotated[str | None, typer.Option(help="target to build")] = None,
    labels: Annotated[
        list[str] | None, typer.Option("--label", help="add label to container")
    ] = None,
    rechunk: Annotated[bool, typer.Option(help="run rechunk after build")] = False,
    rechunk_image: Annotated[
        str | None, typer.Option(help="image to use for rechunking")
    ] = None,
    iidfile: Annotated[
        str | None, typer.Option(help="path to write image ID to")
    ] = None,
    push: Annotated[bool, typer.Option(help="push image after build")] = False,
    private_key: Annotated[
        str | None, typer.Option(help="path to sigstore private key to sign with")
    ] = None,
    passphrase_file: Annotated[
        str | None,
        typer.Option(help="path to file containing passphrase to decrypt private key"),
    ] = None,
):
    """Build (and possibly rechunk, sign, or push) a container with Podman"""

    if rechunk and os.getuid() != 0:
        raise Exception("rechunking must be done as root")

    tags = [tag] if tag else []
    labels = labels or []

    if os.environ.get("DOCKER_METADATA_OUTPUT_JSON", ""):
        parse_docker_metadata(tags, labels)

    if not len(tags):
        raise Exception("no tags specified; try passing --tag?")

    base_tag = tags[0].split("/")[-1].split(":")[0]
    tmp_tag = f"localhost/{base_tag}:tmp-{datetime.now().strftime('%y%m%d%H%M%S')}"
    build_argv = ["--network=host", "--pull=newer", f"--tag={tmp_tag}"]

    for label in labels:
        build_argv.append(f"--label={label}")

    if filename is not None:
        build_argv += ["-f", filename]

    if target is not None:
        build_argv.append(f"--target={target}")

    build_argv += [context]
    _ = subprocess.run(["podman", "build"] + build_argv, check=True)

    if rechunk:
        tmp_tag = do_rechunk(tmp_tag, base_tag, rechunk_image)

    if iidfile:
        write_iidfile(tmp_tag, iidfile)

    _ = subprocess.run(["podman", "tag", tmp_tag] + tags, check=True)

    if push:
        push_argv = make_push_argv(private_key, passphrase_file)
        for tag in tags:
            _ = subprocess.run(["podman", "push"] + push_argv + [tag], check=True)
