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
2. Set it as the default IngressClass: `kubectl annotate ingressclass your-ingress-class ingressclass.kubernetes.io/is-default-class=true`
3. Choose a domain for challenges to be exposed on subdomains, eg `chals.example.com`
4. `ctf plugins deploy_k8s --registry ghcr.io/username --challenge challengefolder --domain chals.example.com`
5. Configure DNS for `*.chals.example.com` to point to your ingress controller external IP address
6. Visit your challenge at `http://challenge-name.chals.example.com`
7. (Optional) Configure TLS termination at the ingress controller. If using the Ingress TLS field, create a Kubernetes secret in the challenge namespace named `listener-tls-secret` or use `--ingressTlsSecret`. This can be automated with [reflector](https://github.com/emberstack/kubernetes-reflector) for wildcard certificates (recommended) or [cert-manager](https://cert-manager.io/).

`--ingressClassName` is available to support non-default ingress classes.

## Private container registries
To use a private container registry with password authentication, add `--registrySecret secret-name` and create a Kubernetes secret in the challenge namespace. 

This can be done automatically:

```sh
output=$(ctf plugins deploy_k8s ghcr.io/username chals.example.com)
echo $output
namespace=$(echo $output | rev | cut -d " " -f1 | rev)
kubectl create secret docker-registry ghcr --namespace=$namespace \
--docker-server=ghcr.io \
--docker-username=username \
--docker-password=password
```
