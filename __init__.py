from types import MethodType
from ctfcli.utils.challenge import (
	load_challenge,
)
from ctfcli.utils.config import (
    load_config,
)

import os
from pathlib import Path
import re
import subprocess
import tempfile

import click
import yaml
from slugify import slugify

# TODO replace ingress and annotations with strategic merge patch
def deploy_kubernetes(self, registry, registrySecret=None, challenge=None, domain=None,
	ingressClassName=None, ingressTlsSecret=None, annotations=None):
	# boilerplate from https://github.com/CTFd/ctfcli/blob/7b4a09af8414eb1f5f6da9a8422fb53b5e9cbc15/ctfcli/cli/challenges.py#L301
	if challenge is None:
		challenge = os.getcwd()

	path = Path(challenge)

	if path.name.endswith(".yml") is False:
		path = path / "challenge.yml"

	click.secho(f"Found {path}")
	challenge = load_challenge(path)
	click.secho(f'Loaded {challenge["name"]}', fg="yellow")

	# autodetect category for convenience, unlike ctfcli
	category = getattr(challenge, "category", str(challenge.directory.parent))
	namespace = slugify(f"{category}-{challenge['name']}")

	# https://github.com/kubernetes/kompose/blob/17fbe3b4632cca0f61a7fda5f3b91034cdf5c5e4/pkg/app/app.go#L35-L43
	defaultComposeFiles = ["compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"]
	composeFiles = [p for p in [Path(challenge.directory, f) for f in defaultComposeFiles] if os.path.isfile(p)]
	if not composeFiles:
		click.secho(
			f"Couldn\'t find docker-compose file for challenge {challenge['name']}",
			fg="red",
		)
		return

	compose = composeFiles[-1]
	if len(composeFiles) > 1:
		click.secho(
			f"Multiple docker-compose files found for challenge {challenge['name']}. Defaulting to {compose}",
			fg="yellow",
		)

	with open(compose) as f:
		doc = yaml.safe_load(f)

	services = doc.get("services", {})
	portRegex = re.compile(r".*:(.+)")
	for key in services:
		labels = services[key].setdefault("labels", {})

		# https://docs.docker.com/compose/compose-file/compose-file-v3/#ports
		ports = services[key].get("ports", [])
		for i, port in enumerate(ports):
			if (type(port) is str):
				# 80:80 -> 80 to prevent hostPorts
				ports[i] = re.sub(portRegex, r"\1", port)
				
				if domain:
					# detect primary service by name
					hostname = slugify(challenge['name'] if key == "app" else f"{challenge['name']}-{key}")

					labels.setdefault("kompose.service.expose.tls-secret", hostname if ingressTlsSecret else "listener-tls-secret")
					hostname = f"{hostname}.{domain}"
				else:
					hostname = "true"
				labels.setdefault("kompose.service.expose", hostname)

				# TODO custom property to control this on a per-service basis
				if category == "pwn" or challenge.get("protocol", False) == "tcp":
					labels.setdefault("kompose.service.type", "loadbalancer")
				elif ingressClassName:
					labels.setdefault("kompose.service.expose.ingress-class-name", ingressClassName)

				if annotations:
					for k, v in annotations:
						labels.setdefault(k, v)

			else:
				# kompose doesn't support long syntax as of writing
				click.secho(
					f"docker-compose port long syntax in challenge {challenge['name']} is not supported",
					fg="yellow",
				)

		if registrySecret is not None:
			labels.setdefault("kompose.image-pull-secret", registrySecret)
		
		# git dependency, not strictly necessary but prevents k8s redeploys if image hasn't changed
		sha = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()
		services[key].setdefault("image", f"{registry}/{namespace}/{key}:{sha}")

	with tempfile.TemporaryDirectory() as tmp:
		subprocess.run([
			"kompose", "convert",
			"-f", "-",
			"--out", tmp,
			"--namespace", namespace,
			"--with-kompose-annotation=false",
			"--build", "local",
			"--push-image",
			"--verbose",
		], cwd=challenge.directory, input=yaml.dump(doc), text=True)

		# deploy namespace first so we can use it in the other manifests
		subprocess.call(["kubectl", "apply", "-f", Path(tmp, "*-namespace.yaml")])
		
		# use ApplySet pruning (alpha in v1.27) to select resources, since labels aren't sufficient and standalone namespacing isn't supported
		env = os.environ.copy()
		env["KUBECTL_APPLYSET"] = "true"
		subprocess.call([
			"kubectl", "apply",
			"-f", tmp,
			"--prune",
			"--namespace", namespace,
			"--applyset", namespace
		], env=env)

	# TODO set connection_info on challenge
	# https://github.com/CTFd/ctfcli/blob/7b4a09af8414eb1f5f6da9a8422fb53b5e9cbc15/ctfcli/cli/challenges.py#L342

	# write to stdout by default eg for automatic secret creation
	# we don't want to handle secrets, since implementations can vary a lot
	return namespace

def load(commands):
	plugins = commands["plugins"]
	plugins.deploy_k8s = MethodType(deploy_kubernetes, plugins)
