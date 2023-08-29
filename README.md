# ctfcli-deploy-kubernetes

A [ctfcli](https://github.com/CTFd/ctfcli) plugin for deploying CTF challenge containers to Kubernetes.

## Installation

1. Install the plugin: `ctf plugins install https://github.com/pl4nty/ctfcli-deploy-kubernetes`
2. [Install Kompose](https://kompose.io/installation/)
3. Install `kubectl` and configure cluster access, eg [Google Kubernetes Engine docs](https://cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl)
4. Login to a container registry, eg `docker login ghcr.io`

## Usage

1. Add a [Compose](https://www.compose-spec.io/) file like `docker-compose.yml` to your challenge folder
2. `ctf plugins deploy_k8s --registry ghcr.io/username --challenge challengefolder`

## Pwn challenges

To expose pwn challenges to the internet:

1. Ensure challenges have unique ports
2. Choose a domain for challenges to be exposed on subdomains, eg `chals.example.com`
3. `ctf plugins deploy_k8s --registry ghcr.io/username --challenge challengefolder --domain chals.example.com`
4. Configure DNS for `chals.example.com` to point to your cloud provider's load balancer external IP address
5. Visit your challenge at `chals.example.com:1234`

## Web challenges

To expose web challenges to the internet:

1. [Install an ingress controller](https://kubernetes.io/docs/concepts/services-networking/ingress-controllers/)
2. Set it as the default IngressClass: `kubectl annotate ingressclass your-ingress-class ingressclass.kubernetes.io/is-default-class=true`. Alternatively, set `kompose.service.expose.tls-secret` in a [template](#templating)
3. Choose a domain for challenges to be exposed on subdomains, eg `chals.example.com`
4. `ctf plugins deploy_k8s --registry ghcr.io/username --challenge challengefolder --domain chals.example.com`
5. Configure DNS for `*.chals.example.com` to point to your ingress controller external IP address
6. Visit your challenge at `http://challenge-name.chals.example.com`
7. (Optional) Configure TLS termination at the ingress controller. If using the Ingress TLS field, create a Kubernetes secret in the challenge namespace and set `kompose.service.expose.tls-secret` in a [template](#templating). Secret creation can be automated with [reflector](https://github.com/emberstack/kubernetes-reflector) for wildcard certificates (recommended) or [cert-manager](https://cert-manager.io/).

## Private container registries

To use a private container registry with password authentication, create a Kubernetes secret in the challenge namespace. Secret creation can be automated with [reflector](https://github.com/emberstack/kubernetes-reflector).

```sh
kubectl create secret docker-registry ghcr --namespace=$namespace \
--docker-server=ghcr.io \
--docker-username=username \
--docker-password=password
```

Then set `kompose.image-pull-secret` in a [template](#templating).

## Templating

Use `--template` with a [Compose](https://www.compose-spec.io/) file to merge it into challenges. This can enable certain features. For a full list of supported `kompose` labels, see the labels section of the [Kompose docs](https://kompose.io/user-guide/).

```yaml
services:
  app:
    labels:
      kompose.image-pull-secret: 'mypullsecretname'
      kompose.service.expose.ingress-class-name: 'myingressclass'
      kompose.service.expose.tls-secret: 'mytlssecretname'
```
