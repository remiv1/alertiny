# Déploiement avec Podman

Ce guide décrit le déploiement prévu pour la V1 : un conteneur Podman unique qui exécute l'API et le scheduler. Le stockage de la file est une base SQLite persistée dans un volume. Le conteneur n'inclut ni terminaison TLS HTTP, ni mécanisme de réplication ou de haute disponibilité.

## Prérequis

- Podman installé sur l'hôte.
- Un serveur SMTP et un serveur IMAP accessibles depuis le conteneur.
- Un volume persistant pouvant contenir `/data/alertiny.db`.
- Une configuration valide dans `src/config/config.yaml` et un fichier d'environnement privé dérivé de `src/config/.env.example`.

## Configurer le service

Avant la construction de l'image, configurez `src/config/config.yaml` :

- `mail.from` : adresse expéditrice.
- `mail.smtp.server` et `mail.smtp.port` : serveur et port SMTP.
- `mail.smtp.tls` et `mail.smtp.starttls` : activer exactement l'un des deux modes.
- `mail.retries` : nombre de tentatives supplémentaires après le premier essai.
- `mail.imap.server`, `mail.imap.port` et `mail.imap.folder` : destination de la copie
  des messages envoyés.
- `mail.imap.copy_to_sent` doit rester activé en V1.
- `mail.imap.tls` et `mail.imap.starttls` : activer exactement l'un des deux modes.

Créez un fichier d'environnement non versionné à partir de `src/config/.env.example`. Renseignez-y `ALERTINY_BEARER_TOKEN`, `SMTP_USERNAME` et `SMTP_PASSWORD`. Le jeton Bearer doit être long et aléatoire. `IMAP_USERNAME` et `IMAP_PASSWORD` sont facultatifs; en leur absence, Alertiny reprend les identifiants SMTP. Pour chaque protocole, le nom d'utilisateur et le mot de passe doivent être fournis ensemble.

Ne placez pas de secrets dans `config.yaml` ni dans l'image. Le fichier d'environnement doit être lisible uniquement par le compte qui lance Podman. Si les serveurs utilisent une autorité de certification interne, ajoutez son certificat au magasin de confiance de l'image avant de la construire; la vérification des certificats est activée.

## Construire et démarrer

Depuis la racine du dépôt, construisez l'image :

```sh
podman build -f src/containerfile -t alertiny:local .
```

Créez un volume nommé puis lancez le conteneur. Remplacez le chemin de l'exemple par celui du fichier d'environnement privé préparé à l'étape précédente :

```sh
podman volume create alertiny-data
podman run -d \
  --name alertiny \
  -p 127.0.0.1:8465:8465 \
  -v alertiny-data:/data:Z \
  --env-file /chemin/vers/alertiny.env \
  alertiny:local
```

Le port `8465` est le port HTTP configuré par défaut dans l'image. La publication sur `127.0.0.1` limite l'accès à l'hôte; pour un accès distant, placez l'API derrière un reverse proxy configuré en HTTPS et contrôlez les règles réseau. `/health` ne demande pas de jeton et doit rester réservé aux sondes et aux contrôles de disponibilité.

Sur un hôte Linux avec SELinux, le suffixe `:Z` étiquette le volume pour l'usage privé de ce conteneur. Si votre système n'utilise pas SELinux et que Podman ne reconnaît pas cette option, utilisez `-v alertiny-data:/data`.

Les paramètres SMTP/IMAP et les templates sont copiés dans l'image à la construction. Après une modification de `src/config/config.yaml` ou des templates, reconstruisez l'image et recréez le conteneur en conservant le volume `alertiny-data`.

## Vérifier et exploiter

Vérifiez l'état de l'API et sa connexion à la base :

```sh
curl --fail --silent http://127.0.0.1:8465/health
```

La réponse contient les états `API`, `DATABASE` et `ENVIRONMENT`. `API` et `DATABASE` doivent valoir `OK`; `ENVIRONMENT` indique si le jeton Bearer requis est présent. La réponse peut mentionner le nom d'une variable manquante, jamais sa valeur.

Consultez les journaux ou arrêtez le conteneur avec :

```sh
podman logs -f alertiny
podman stop alertiny
```

Le volume nommé conserve la base après l'arrêt ou la suppression du conteneur. Une seule instance du scheduler doit traiter une base SQLite donnée : ne lancez pas plusieurs conteneurs partageant `alertiny-data`. Le scheduler est inclus dans le conteneur; il ne doit pas être lancé séparément pour le même volume.

## Limites opérationnelles

- Les données de la file sont locales au volume SQLite; prévoyez une sauvegarde cohérente du volume et une procédure de restauration adaptées à votre exploitation.
- L'envoi SMTP et la transaction SQLite ne sont pas atomiques. Une interruption après acceptation SMTP mais avant l'enregistrement de cet état peut entraîner un nouvel envoi à la reprise.
- Les routes de l'API, sauf `/health`, exigent `Authorization: Bearer`. L'API ne fournit pas elle-même de terminaison HTTPS.
- La configuration actuelle n'expose pas de métriques ni de mécanisme de rotation de sauvegardes. Surveillez les journaux du conteneur et l'espace du volume.
