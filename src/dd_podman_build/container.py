import json
import logging
import os
import subprocess
import tempfile
import time
from datetime import datetime
from functools import partial
from pathlib import Path

import typer
from typing_extensions import Annotated

from .authfile import find_authfile
from .logging import configure_logging
from .run import run

app = typer.Typer()


def parse_docker_metadata(tags: list[str] = [], labels: list[str] = []):
    metadata = json.loads(os.environ["DOCKER_METADATA_OUTPUT_JSON"])

    if not isinstance(metadata, dict):
        raise Exception("Malformed DOCKER_METADATA_OUTPUT_JSON: top-level not a dict")

    if "tags" in metadata:
        if not isinstance(metadata["tags"], list):
            raise Exception("Malformed DOCKER_METADATA_OUTPUT_JSON: tags not a list")

        for metadata_tag in map(str, metadata["tags"]):
            if metadata_tag not in tags:
                tags.append(metadata_tag)

    if "labels" in metadata:
        if not isinstance(metadata["labels"], dict):
            raise Exception("Malformed DOCKER_METADATA_OUTPUT_JSON: labels not a dict")

        for key, value in metadata["labels"].items():
            metadata_label = f"{key}={value}"
            if metadata_label not in tags:
                labels.append(metadata_label)

    return (tags, labels)


def do_rechunk(tmp_tag: str, base_tag: str, rechunk_image: str | None) -> str:
    rechunk_image = rechunk_image or os.environ.get(
        "RECHUNK_IMAGE", "quay.io/centos-bootc/centos-bootc:stream9"
    )
    rechunk_tag = f"localhost/{base_tag}:tmp-{datetime.now().strftime('%y%m%d%H%M%S')}"

    _ = run(
        "sudo",
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
        log_as="podman",
    )

    return rechunk_tag


def write_iidfile(inspection: str, iidfile: str):
    inspection = json.loads(inspection)
    if not isinstance(inspection, list):
        raise Exception("`podman inspect` output is not a list")
    if len(inspection) > 1:
        raise Exception("`podman inspect` returrned more than one image")

    inspection = inspection[0]
    if not isinstance(inspection, dict):
        raise Exception("`podman inspect` list doesn't contain a dict")

    image_id = inspection.get("Id", None)
    if not isinstance(image_id, str):
        raise Exception("`podman inspect` output missing or malformed image ID")

    with open(iidfile, "w") as iid_out:
        _ = iid_out.write(image_id)


def make_podman_args(sudo: bool):
    if sudo:
        authfile = find_authfile()
        if authfile:
            return partial(
                run,
                "sudo",
                "env",
                f"REGISTRY_AUTH_FILE={authfile}",
                "podman",
                log_as="podman",
            )

        return partial(run, "sudo", "podman", log_as="podman")

    return partial(run, "podman")


def do_push(podman: partial[subprocess.CompletedProcess[str]], tag: str, sign: bool):
    with tempfile.TemporaryDirectory() as tmp:
        digestfile = Path(tmp) / "digest"
        for tries_left in range(4, -1, -1):
            try:
                _ = podman("push", "--digestfile", digestfile, tag)
                break
            except subprocess.CalledProcessError:
                if not tries_left:
                    raise
                logging.warning(
                    f"push failed, sleeping 5 seconds (tries remaining: {tries_left})"
                )
                time.sleep(5)
        with open(digestfile) as digest_in:
            digest = digest_in.read().strip()

    if sign:
        base_tag = tag.split(":")[0]
        digest_tag = f"{base_tag}@{digest}"
        _ = run("cosign", "sign", "-y", "--key", "env://COSIGN_PRIVATE_KEY", digest_tag)

    return digest


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
    rechunk: Annotated[
        bool, typer.Option(help="run rechunk after build (implies sudo)")
    ] = False,
    rechunk_image: Annotated[
        str | None, typer.Option(help="image to use for rechunking")
    ] = None,
    sudo: Annotated[bool | None, typer.Option(help="run podman as root")] = None,
    iidfile: Annotated[
        str | None, typer.Option(help="path to write image ID to")
    ] = None,
    push: Annotated[bool, typer.Option(help="push image after build")] = False,
    sign: Annotated[bool | None, typer.Option(help="sign the container")] = None,
    verbose: Annotated[bool, typer.Option(help="be noisy")] = False,
):
    """Build (and possibly rechunk, sign, or push) a container with Podman"""
    configure_logging(verbose)

    if rechunk:
        if sudo is not None and not sudo:
            raise Exception("must sudo when rechunking")
        sudo = True
    else:
        sudo = sudo or False

    if sign:
        if "COSIGN_PRIVATE_KEY" not in os.environ:
            raise Exception("COSIGN_PRIVATE_KEY should be set")
    elif sign is None:
        sign = "COSIGN_PRIVATE_KEY" in os.environ

    if sign and " ENCRYPTED " in os.environ["COSIGN_PRIVATE_KEY"]:
        if "COSIGN_PASSWORD" not in os.environ:
            raise Exception("COSIGN_PASSWORD should be set")

    podman = make_podman_args(sudo)
    tags = [tag] if tag else []
    labels = labels or []

    if os.environ.get("DOCKER_METADATA_OUTPUT_JSON", ""):
        logging.info("parsing Docker metadata from environment")
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
    logging.info("Building container...")
    _ = podman("build", *build_argv)

    if rechunk:
        logging.info("Rechunking container...")
        tmp_tag = do_rechunk(tmp_tag, base_tag, rechunk_image)

    if iidfile:
        logging.info(f"Writing iidfile {iidfile}...")
        inspection = podman(
            "inspect",
            tmp_tag,
            stdout=subprocess.PIPE,
        ).stdout
        write_iidfile(inspection, iidfile)

    _ = podman("tag", tmp_tag, *tags)

    if push:
        for tag in tags:
            logging.info(f"Pushing tag {tag}...")
            do_push(podman, tag, sign)
