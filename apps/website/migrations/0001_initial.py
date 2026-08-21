from django.db import migrations, models
import django.db.models.deletion


def seed_areas(apps, schema_editor):
    StayArea = apps.get_model("website", "StayArea")
    areas = [
        {
            "name": "Puteaux & La Défense",
            "slug": "puteaux-la-defense",
            "summary": "Une base pratique pour rejoindre rapidement la mairie, l'église et le vin d'honneur.",
            "advantages": "Offre de transports et de logements variée, commerces et restauration à proximité.",
            "considerations": "Prévoyez le trajet vers Ris-Orangis après les cérémonies.",
            "transport_notes": "Particulièrement adaptée aux invités privilégiant les transports en commun.",
            "recommended_for": "Priorité aux cérémonies",
            "search_query": "hébergements Puteaux La Défense",
            "display_order": 10,
            "is_published": True,
        },
        {
            "name": "Ris-Orangis & environs",
            "slug": "ris-orangis",
            "summary": "Une option confortable pour limiter le trajet de retour après le dîner et la soirée.",
            "advantages": "Retour plus simple en fin de soirée, notamment en voiture ou en taxi.",
            "considerations": "Les cérémonies du matin se déroulent à Puteaux, plus au nord.",
            "transport_notes": "Vérifiez les horaires de transport tardifs et les possibilités de stationnement.",
            "recommended_for": "Priorité à la soirée",
            "search_query": "hébergements Ris-Orangis",
            "display_order": 20,
            "is_published": True,
        },
        {
            "name": "Sud parisien, compromis voiture",
            "slug": "compromis-sud-parisien",
            "summary": "Une zone intermédiaire à envisager pour équilibrer les déplacements entre Puteaux et Ris-Orangis.",
            "advantages": "Répartition plus équilibrée des kilomètres sur l'ensemble de la journée.",
            "considerations": "La circulation peut modifier fortement les durées : comparez chaque trajet avant de réserver.",
            "transport_notes": "Option surtout pertinente pour les invités disposant d'une voiture.",
            "recommended_for": "Compromis entre les lieux",
            "search_query": "hébergements sud Paris accès A6",
            "display_order": 30,
            "is_published": True,
        },
    ]
    for values in areas:
        StayArea.objects.update_or_create(slug=values["slug"], defaults=values)


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="StayArea",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, verbose_name="nom")),
                ("slug", models.SlugField(unique=True)),
                ("summary", models.TextField(verbose_name="présentation")),
                ("advantages", models.TextField(blank=True, verbose_name="atouts")),
                ("considerations", models.TextField(blank=True, verbose_name="points d'attention")),
                ("transport_notes", models.TextField(blank=True, verbose_name="conseils de transport")),
                ("recommended_for", models.CharField(blank=True, max_length=240, verbose_name="profil conseillé")),
                ("search_query", models.CharField(blank=True, max_length=240, verbose_name="recherche Google Maps")),
                ("display_order", models.PositiveSmallIntegerField(default=0, verbose_name="ordre")),
                ("checked_at", models.DateField(blank=True, null=True, verbose_name="vérifié le")),
                ("is_published", models.BooleanField(default=False, verbose_name="publié")),
            ],
            options={"verbose_name": "zone de séjour", "verbose_name_plural": "zones de séjour", "ordering": ["display_order", "name"]},
        ),
        migrations.CreateModel(
            name="Accommodation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160, verbose_name="nom")),
                ("accommodation_type", models.CharField(choices=[("hotel", "Hôtel"), ("aparthotel", "Appart'hôtel"), ("rental", "Location saisonnière")], max_length=20, verbose_name="type")),
                ("address", models.CharField(blank=True, max_length=255, verbose_name="adresse")),
                ("booking_url", models.URLField(max_length=1000, verbose_name="lien de réservation")),
                ("price_level", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="niveau de prix")),
                ("capacity_note", models.CharField(blank=True, max_length=120, verbose_name="capacité")),
                ("has_parking", models.BooleanField(null=True, verbose_name="stationnement")),
                ("near_public_transport", models.BooleanField(null=True, verbose_name="proche des transports")),
                ("is_accessible", models.BooleanField(null=True, verbose_name="accessible PMR")),
                ("editorial_note", models.TextField(blank=True, verbose_name="note")),
                ("checked_at", models.DateField(blank=True, null=True, verbose_name="vérifié le")),
                ("display_order", models.PositiveSmallIntegerField(default=0, verbose_name="ordre")),
                ("is_published", models.BooleanField(default=False, verbose_name="publié")),
                ("area", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="accommodations", to="website.stayarea")),
            ],
            options={"verbose_name": "logement", "verbose_name_plural": "logements", "ordering": ["display_order", "name"]},
        ),
        migrations.RunPython(seed_areas, migrations.RunPython.noop),
    ]
