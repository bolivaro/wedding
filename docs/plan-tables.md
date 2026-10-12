# Plan de tables du dîner

Accès : Administration → Invités → Plan de tables — Dîner.

Les utilisateurs avec la permission `guests.view_guest` peuvent consulter le plan.
La permission `guests.change_guest` permet de créer des tables, affecter, déplacer,
retirer et échanger les convives. Chaque table comporte exactement 10 places au maximum.

Seules les présences effectives confirmées à l’événement actif de code `reception`
sont proposées. Les réponses en attente, absences, invités inactifs et non éligibles
sont exclus. Les disponibilités personnalisées des accompagnants sont respectées.
La recherche porte sur le nom, le groupe et l’invité principal. Plusieurs cases
peuvent être cochées pour une affectation collective atomique.

Une affectation devenue incompatible avec la présence apparaît comme anomalie.
Elle réserve sa place jusqu’à son retrait explicite. Les compteurs « placés » et
« à placer » ne comptent que les convives actuellement confirmés. Les échanges
permettent de permuter deux personnes entre tables complètes.

## Déploiement Railway

1. Déployer les commits de `feature/plantable` via le processus habituel.
2. Exécuter `python manage.py migrate --noinput` dans l’environnement Railway
   utilisant le nouveau code et la base PostgreSQL de l’application, avant
   d’ouvrir la nouvelle interface. Si un pre-deploy command existe, y intégrer
   cette commande. Le script `start.sh` actuel ne lance pas les migrations.
3. Le démarrage existant exécute déjà `collectstatic --noinput` ; il collecte
   donc les nouveaux fichiers CSS et JavaScript.
4. Vérifier l’accès au plan avec un compte admin, créer une table et affecter
   un convive confirmé. Vérifier aussi le thème sombre et un écran mobile.

La migration `0017_dinnertable_dinnerseatingassignment` crée seulement deux
nouvelles tables. Aucun invité n’est affecté automatiquement, aucune migration
existante n’est modifiée et les QR ne changent pas. Aucune nouvelle variable
d’environnement ni dépendance n’est nécessaire.

Pour revenir au code précédent, conserver les nouvelles tables en base : ne pas
annuler la migration après avoir commencé à enregistrer les affectations.

## Vérification locale isolée

```sh
DATABASE_URL=sqlite:////tmp/wedding-seating-check.sqlite3 .venv/bin/python manage.py test tests.test_dinner_seating tests.test_guest_capacity --noinput
DATABASE_URL=sqlite:////tmp/wedding-seating-check.sqlite3 .venv/bin/python manage.py makemigrations --check --dry-run
```

Les verrous utilisés pour sérialiser les affectations sont effectifs sur PostgreSQL.
Les tests SQLite vérifient les règles métier mais ne simulent pas la concurrence PostgreSQL.
