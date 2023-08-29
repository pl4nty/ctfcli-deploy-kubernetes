import logging
import os
import subprocess
import tempfile
import re
from pathlib import Path
from types import MethodType

import click
import hiyapyco
from slugify import slugify

from ctfcli.core.challenge import Challenge
from ctfcli.core.config import Config
from ctfcli.core.exceptions import ChallengeException

log = logging.getLogger("ctfcli.cli.challenges")

# TODO replace ingress and annotations with strategic merge patch
def deploy_kubernetes(
	self,
	registry: str,
	challenge: str = None,
	domain: str = None,
	template: str = None,
	registrySecret=None, ingressTlsSecret=None
) -> str:
	# boilerplate from https://github.com/CTFd/ctfcli/blob/c385e70c5553dea013b1b6c99fbe353324e5f3fe/ctfcli/cli/challenges.py#L621
	log.debug(f"deploy_k8s: (registry={registry}, challenge={challenge}, domain={domain}, template={template})")
	
	config = Config()
	challenge_keys = [challenge]

	if challenge is None:
		challenge_keys = config.challenges.keys()

	failed_deployments = []

	deployable_challenges = []
	for challenge_key in challenge_keys:
		challenge_path = config.project_path / Path(challenge_key)

		if not challenge_path.name.endswith(".yml"):
			challenge_path = challenge_path / "challenge.yml"

		try:
			challenge = Challenge(challenge_path)

			# https://github.com/kubernetes/kompose/blob/17fbe3b4632cca0f61a7fda5f3b91034cdf5c5e4/pkg/app/app.go#L35-L43
			defaultComposeFiles = ["compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"]
			composeFiles = [p for p in [Path(challenge.challenge_directory, f) for f in defaultComposeFiles] if os.path.isfile(p)]
			if len(composeFiles) > 1:
				click.secho(
					f"Multiple docker-compose files found for challenge {challenge['name']}. Defaulting to {compose}",
					fg="yellow",
				)

			if composeFiles:
				deployable_challenges.append((challenge, composeFiles[-1]))

		except ChallengeException as e:
			click.secho(str(e), fg="red")
			failed_deployments.append(challenge_key)
			continue

	with click.progressbar(deployable_challenges, label="Deploying challenges") as challenges:
		for (challenge, compose) in challenges:
			click.echo()

			if template:
				doc = hiyapyco.load(str(compose), template, method=hiyapyco.METHOD_MERGE)
			else:
				doc = hiyapyco.load(str(compose), method=hiyapyco.METHOD_MERGE)
			
			namespace = slugify(f"{challenge['category']}-{challenge['name']}")
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

						# TODO custom property to control this on a per-service basis
						if challenge['category'] == "pwn" or challenge.get("protocol", False) == "tcp":
							labels.setdefault("kompose.service.type", "loadbalancer")
							if key == "app":
								challenge['connection_info'] = f"nc {domain} {ports[i]}"
						else:
							if domain:
								# detect primary service by name
								hostname = slugify(challenge['name'] if key == "app" else f"{challenge['name']}-{key}")
								hostname = f"{hostname}.{domain}"

								if key == "app":
									challenge['connection_info'] = f"{challenge.get('protocol', 'https')}://{hostname}"

							else:
								hostname = "true"
							labels.setdefault("kompose.service.expose", hostname)

					else:
						# kompose doesn't support long syntax as of writing
						click.secho(
							f"docker-compose port long syntax in challenge {challenge['name']} is not supported",
							fg="yellow",
						)
				
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
				], cwd=challenge.challenge_directory, input=hiyapyco.dump(doc), text=True)

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

			challenge.sync()

	return 1

def load(commands):
	plugins = commands["plugins"]
	plugins.deploy_k8s = MethodType(deploy_kubernetes, plugins)
