# based on https://github.com/CTFd/ctfcli/blob/0.1.1/ctfcli/core/deployment/registry.py

import logging
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlparse, parse_qs

import click
import hiyapyco
from slugify import slugify

from ctfcli.core.config import Config
from ctfcli.core.deployment import register_deployment_handler
from ctfcli.core.deployment.base import DeploymentHandler, DeploymentResult
from ctfcli.core.deployment.registry import RegistryDeploymentHandler
from ctfcli.core.deployment.cloud import CloudDeploymentHandler

log = logging.getLogger("ctfcli.core.deployment.kubernetes")


class KubernetesDeploymentHandler(DeploymentHandler):
    def __init__(self, *args, **kwargs):
        super(KubernetesDeploymentHandler, self).__init__(*args, **kwargs)

        # default to tcp for pwn challenges and https for web
        if self.challenge.get("protocol", False):
            if self.challenge.get("category") == "pwn":
                self.protocol = "tcp"
            elif self.challenge.get("category") == "web":
                self.protocol = "https"

    def deploy(self, skip_login=False, *args, **kwargs) -> DeploymentResult:
        config = Config()

        # Check whether challenge defines image
        # Unnecessary, but ensures compatibility with other deployment handlers
        if not self.challenge.get("image"):
            click.secho("Challenge does not define an image to deploy", fg="red")
            return DeploymentResult(False)

        if not self.host:
            click.secho(
                "No host provided for the deployment. Use --host, or define host in the challenge.yml file",
                fg="red",
            )
            return DeploymentResult(False)

        # kubernetes://public-hostname?registry=ghcr.io/pl4nty&override=compose.override.yml
        host_url = urlparse(self.host)
        query = parse_qs(host_url.query)
        registry = query.get("registry", None)
        if registry:
            registry = registry[0]
        override = query.get("override", None)
        if override:
            override = override[0]

        if skip_login:
            click.secho(
                "Skipping registry login because of --skip-login. Make sure you are logged in to the registry.",
                fg="yellow",
            )
        else:
            if "registry" not in config or not config["registry"]:
                click.secho("Config does not provide a registry section.", fg="red")
                return DeploymentResult(False)

            registry_username = config["registry"].get("username")
            registry_password = config["registry"].get("password")
            if not registry_username or not registry_password:
                click.secho("Config is missing credentials for the registry.", fg="red")
                return DeploymentResult(False)

            if not registry:
                click.secho("Host is missing registry query parameter.", fg="red")
                return DeploymentResult(False)

            login_result = RegistryDeploymentHandler._registry_login(
                registry_username,
                registry_password,
                registry,
            )

            if not login_result:
                click.secho(
                    "Could not log in to the registry. Please check your configured credentials.",
                    fg="red",
                )
                return DeploymentResult(False)

        # Check whether challenge has a compose file. Can't use kompose because defaults are skipped if we provide an override file
        # https://github.com/kubernetes/kompose/blob/v1.31.2/pkg/app/app.go#L38
        defaultComposeFiles = [
            "compose.yaml",
            "compose.yml",
            "docker-compose.yaml",
            "docker-compose.yml",
        ]
        composeFiles = [
            p
            for p in [
                Path(self.challenge.challenge_directory, f) for f in defaultComposeFiles
            ]
            if os.path.isfile(p)
        ]
        if len(composeFiles) == 0:
            click.secho("Challenge does not have a Compose file.", fg="red")
            return DeploymentResult(False)
        elif len(composeFiles) > 1:
            click.secho(
                f"Challenge has multiple Compose files. Defaulting to {composeFiles[0]}",
                fg="yellow",
            )

        doc = hiyapyco.load(str(composeFiles[0]))
        services = doc.get("services", {})
        connection_info = None
        for i, key in enumerate(services):
            # https://challenge-name-service-name.domain, or https://challenge-name.domain for the primary service
            hostname = slugify(self.challenge.get("name"))
            if i > 0:
                hostname += f"-{key}"
            hostname += f".{host_url.netloc}"

            # set CTFd metadata for primary service
            if key == 0:
                ports = services[key].get("ports", [])
                if len(ports) > 0:
                    connection_info = CloudDeploymentHandler._get_connection_info(
                        self,
                        hostname=hostname,
                        tcp_hostname=host_url.netloc,
                        tcp_port=ports[0].split(":")[0],
                    )

            labels = services[key].setdefault("labels", {})
            if self.protocol == "tcp":
                labels.setdefault("kompose.service.type", "loadbalancer")
            else:
                labels.setdefault("kompose.service.expose", hostname)

            namespace = slugify(self.challenge.get("name"))
            if registry:
                services[key].setdefault("image", f"{registry}/{namespace}/{key}")

            # output to tmp rather than stdout so we can view logs eg Docker build
            with tempfile.TemporaryDirectory() as tmp:
                params = [
                    "kompose",
                    "convert",
                    # we avoid self.challenge.image.build() since it doesn't support build options from compose eg multiple images
                    "--build",
                    "local",
                    "--namespace",
                    namespace,
                    "--out",
                    tmp,
                    "--push-image",
                    # "--push-image-registry" doesn't support paths eg ghcr.io/pl4nty
                    "--with-kompose-annotation=false",
                    "--file",
                    "-",
                    "--verbose",
                ]
                # if provided, perform a compose merge with the override file
                # https://docs.docker.com/compose/multiple-compose-files/merge/
                if override:
                    params += ["--file", Path.cwd() / override]
                subprocess.run(
                    params,
                    cwd=self.challenge.challenge_directory,
                    input=hiyapyco.dump(doc),
                    text=True,
                )

                # deploy namespace first so we can use it in the other manifests
                subprocess.call(
                    ["kubectl", "apply", "--filename", Path(tmp, "*-namespace.yaml")]
                )

                # use ApplySet pruning (alpha in v1.27) to select resources, since labels aren't sufficient and standalone namespacing isn't supported
                env = os.environ.copy()
                env["KUBECTL_APPLYSET"] = "true"
                subprocess.call(
                    [
                        "kubectl",
                        "apply",
                        "--filename",
                        tmp,
                        "--prune",
                        "--namespace",
                        namespace,
                        "--applyset",
                        namespace,
                    ],
                    env=env,
                )

        return DeploymentResult(True, connection_info=connection_info)


def load(commands):
    register_deployment_handler("kubernetes", KubernetesDeploymentHandler)
