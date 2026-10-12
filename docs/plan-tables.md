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

## Exports pour impression

Deux liens permettent de télécharger un PDF A4 récapitulatif ou un PDF avec
une page par table (précédées d’une couverture récapitulative). Les convives sont
triés par nom et prénom. Dans le PDF récapitulatif, les tables sont affichées
par leur nom, dans l’ordre alphabétique sans distinction de casse ou d’accent.
Seuls les invités actuellement confirmés au dîner
figurent dans les listes des tables. Les tables vides sont incluses.

En présence de convives non placés ou d’affectations incompatibles avec la présence,
le document porte la mention « Plan provisoire ». Une annexe liste les convives à
placer et les affectations exclues à corriger. Les exports sont accessibles avec
la permission `guests.view_guest` et ne modifient aucune donnée.

Aucune migration ou dépendance supplémentaire n’est nécessaire pour cette évolution.

## Nom obligatoire des tables

Le nom est obligatoire à la création, dans le formulaire et côté serveur.
Les noms vides ou composés uniquement d’espaces sont interdits en base.
La migration `0018` nomme les éventuelles tables existantes sans nom « Table N »
puis ajoute cette contrainte, sans toucher aux affectations. Le numéro reste
un identifiant technique interne, attribué automatiquement et absent de l’interface
et des PDF. Les tables sont présentées par leur nom dans l’administration. Appliquer `python manage.py migrate --noinput`
au déploiement (le pre-deploy Railway déjà configuré le fait automatiquement).

La migration `0019` modifie uniquement l’ordre de présentation des tables, sans changement de colonnes ni des affectations.

## Glisser-déposer

Sur ordinateur, glisser un convive depuis « À placer » ou depuis une table vers
une autre table permet de l’affecter ou de le déplacer. Les tables disponibles
sont mises en évidence ; les tables complètes refusent le dépôt. Chaque dépôt
concerne une personne, indépendamment des cases cochées. La sauvegarde utilise
les mêmes contrôles serveur et permissions que les formulaires. Les personnes
en anomalie ne sont pas déplaçables. Sur mobile et au clavier, utiliser les boutons
d’affectation et de déplacement. Aucune migration supplémentaire n’est nécessaire.

## Tables par défaut

La migration `0020` ajoute les 26 noms de tables fournis, sans affecter de convive.
Elle conserve les tables et affectations existantes et ignore les noms déjà présents
(sans distinction de casse ni d’espaces en début ou fin). Elle sera appliquée par
le pre-deploy Railway existant. Son annulation ne supprime aucune table.
