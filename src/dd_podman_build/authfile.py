import os
from functools import cache
from pathlib import Path


@cache
def find_authfile() -> Path | None:
    if "REGISTRY_AUTH_FILE" in os.environ:
        env_config = Path(os.environ["REGISTRY_AUTH_FILE"])
        if env_config.exists():
            return env_config

    docker_config = Path(os.path.expanduser("~")).joinpath(".docker/config.json")
    if docker_config.exists():
        return docker_config

    redhat_config = Path(
        os.getenv("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    ).joinpath("containers/auth.json")
    if redhat_config.exists():
        return redhat_config

    return None
