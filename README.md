# ctfcli-deploy-kubernetes

A [ctfcli](https://github.com/CTFd/ctfcli) plugin for deploying CTF challenge containers to Kubernetes.

## Installation

1. Install the plugin: `ctf plugins install https://github.com/pl4nty/ctfcli-deploy-kubernetes.git`
2. [Install Kompose](https://kompose.io/installation/)
3. Install `kubectl` and configure cluster access, eg [Google Kubernetes Engine docs](https://cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl)
4. Login to a container registry, eg `docker login ghcr.io`

## Usage

1. Add a [Compose](https://www.compose-spec.io/) file like `docker-compose.yml` to your challenge(s)
2. `ctf challenge deploy --host "kubernetes://chals.example.com?registry=ghcr.io/username" --skip-login`
3. If your Compose files already have `image` fields, the registry parameter isn't required
4. If your `.ctf/config` file contains registry credentials, the `--skip-login` parameter isn't requried

## Pwn challenges

To expose pwn challenges to the internet:

1. Ensure challenges have unique ports
2. Choose a domain for challenges to be exposed on subdomains, eg `chals.example.com`
3. `ctf challenge deploy --host "kubernetes://chals.example.com?registry=ghcr.io/username" --skip-login`
4. Configure DNS for `chals.example.com` to point to your cloud provider's load balancer external IP address
5. Visit your challenge eg at `chals.example.com:1234`

## Web challenges

To expose web challenges to the internet:

1. [Install an ingress controller](https://kubernetes.io/docs/concepts/services-networking/ingress-controllers/)
2. Set it as the default IngressClass: `kubectl annotate ingressclass your-ingress-class ingressclass.kubernetes.io/is-default-class=true`. Alternatively, set `kompose.service.expose.tls-secret` in an [override](#overrides)
3. Choose a domain for challenges to be exposed on subdomains, eg `chals.example.com`
4. `ctf challenge deploy --host "kubernetes://chals.example.com?registry=ghcr.io/username" --skip-login`
5. Configure DNS for `*.chals.example.com` to point to your ingress controller external IP address
6. Visit your challenge at `http://challenge-name.chals.example.com`. This will be the first service in the Compose file, other services will be available with the pattern `http://challenge-name-service-name.chals.example.com`
7. (Optional) Configure TLS termination at the ingress controller. If using the Ingress TLS field, create a Kubernetes secret in the challenge namespace and set `kompose.service.expose.tls-secret` in an [override](#override). Secret creation can be automated with [reflector](https://github.com/emberstack/kubernetes-reflector) for wildcard certificates (recommended) or [cert-manager](https://cert-manager.io/).

## Private container registries

To use a private container registry with password authentication, create a Kubernetes secret in the challenge namespace. Secret creation can be automated with [reflector](https://github.com/emberstack/kubernetes-reflector).

```sh
kubectl create secret docker-registry ghcr --namespace=$namespace \
--docker-server=ghcr.io \
--docker-username=username \
--docker-password=password
```

Then set `kompose.image-pull-secret` in an [override](#override).

## Overrides

Use the `override` parameter with a [Compose](https://www.compose-spec.io/) file to [merge](https://docs.docker.com/compose/multiple-compose-files/merge/) it into challenges. This can enable certain features. For a full list of supported `kompose` labels, see the labels section of the [Kompose docs](https://kompose.io/user-guide/).

```yaml
services:
  app:
    labels:
      kompose.image-pull-secret: 'mypullsecretname'
      kompose.service.expose.ingress-class-name: 'myingressclass'
      kompose.service.expose.tls-secret: 'mytlssecretname'
```
