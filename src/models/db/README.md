# Modèle de données

La modélisation de données a un parti pris fondamental : simplicité et conformité.

Le projet aussi petit soit-il doit être capable de répondre à la minimisation des données ainsi qu'à la protection de la vie privée des utilisateurs directs ou indirects.

## Données

```text
┌────────────────────────────┐                       ┌────────────────────────────┐
│          Mails             │                       │          Status            │
│   ══════════════════════   │                       │   ══════════════════════   │
│  - id                      │   <───────┐           │  - id                      │
│  - sender                  │           └─────      │  - mail_id                 │
│  - recipient               │                       │  - status                  │
│  - subject                 │                       │  - comment                 │
│  - template                │                       │  - created_at              │
│  - jinja_values            │                       │  - mail                    │
│  - has_attachments         │                       │                            │
│  - provider_id             │                       │                            │
│  - sent_at                 │                       │                            │
│  - statuses                │                       │                            │
└────────────────────────────┘                       └────────────────────────────┘
```

Le mail destinataire n'est conservé que le temps de l'envoi et n'est pas stocké de manière permanente.
