# `frontend`

Desktop-first DossierAgent command center.

## Owns

- dashboard UI
- watches UI
- listings master-detail UI
- dossier upload and preview UI
- contact packet editor UI
- pending checks and notifications UI
- frontend API client

## Does Not Own

- persistence
- scraping
- ranking
- document extraction
- agent reasoning

## Public Surface

The frontend talks to the backend through the `/api/v1` HTTP contract from the specification.

