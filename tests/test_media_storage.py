from pathlib import PurePosixPath

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import Resolver404, resolve

from guests.models import Guest
from specialdemands.models import SpecialDemand, SpecialDemandSlide


IN_MEMORY_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.InMemoryStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


@override_settings(STORAGES=IN_MEMORY_STORAGES)
class SpecialDemandSlideUploadTests(TestCase):
    def setUp(self):
        guest = Guest.objects.create(
            first_name="Leslie",
            last_name="Test",
            email="leslie@example.com",
        )
        self.special_demand = SpecialDemand.objects.create(
            guest=guest,
            demand_type="witness",
        )

    def test_image_upload_uses_default_storage(self):
        image = SimpleUploadedFile(
            "souvenir.jpg",
            b"fake-image-content",
            content_type="image/jpeg",
        )

        slide = SpecialDemandSlide.objects.create(
            special_demand=self.special_demand,
            position=1,
            text="Un souvenir",
            image=image,
        )

        self.assertEqual(
            PurePosixPath(slide.image.name).parent,
            PurePosixPath("specialdemands/slides"),
        )
        self.assertTrue(default_storage.exists(slide.image.name))
        with default_storage.open(slide.image.name, "rb") as uploaded_file:
            self.assertEqual(uploaded_file.read(), b"fake-image-content")

    def test_uploading_same_filename_does_not_overwrite_existing_file(self):
        first_slide = SpecialDemandSlide.objects.create(
            special_demand=self.special_demand,
            position=1,
            text="Premier souvenir",
            image=SimpleUploadedFile("souvenir.jpg", b"first"),
        )
        second_slide = SpecialDemandSlide.objects.create(
            special_demand=self.special_demand,
            position=2,
            text="Deuxième souvenir",
            image=SimpleUploadedFile("souvenir.jpg", b"second"),
        )

        self.assertNotEqual(first_slide.image.name, second_slide.image.name)
        with default_storage.open(first_slide.image.name, "rb") as first_file:
            self.assertEqual(first_file.read(), b"first")
        with default_storage.open(second_slide.image.name, "rb") as second_file:
            self.assertEqual(second_file.read(), b"second")


class ProductionMediaRoutingTests(TestCase):
    @override_settings(DEBUG=False, OBJECT_STORAGE_ENABLED=True)
    def test_django_does_not_serve_media_in_production(self):
        with self.assertRaises(Resolver404):
            resolve("/media/specialdemands/slides/souvenir.jpg")
