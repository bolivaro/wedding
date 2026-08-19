from pathlib import Path

from django import forms


MAX_IMPORT_SIZE = 10 * 1024 * 1024


class GuestImportUploadForm(forms.Form):
    file = forms.FileField(label="Fichier Excel (.xlsx)")

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]
        if Path(uploaded_file.name).suffix.lower() != ".xlsx":
            raise forms.ValidationError("Seuls les fichiers .xlsx sont acceptés.")
        if uploaded_file.size > MAX_IMPORT_SIZE:
            raise forms.ValidationError("Le fichier ne doit pas dépasser 10 Mo.")
        return uploaded_file


class CompanionForm(forms.Form):
    gender = forms.ChoiceField(label="Civilité", choices=[])
    first_name = forms.CharField(label="Prénom", max_length=100)
    last_name = forms.CharField(label="Nom", max_length=100)

    def __init__(self, *args, **kwargs):
        from guests.models import Guest

        super().__init__(*args, **kwargs)
        self.fields["gender"].choices = [
            (Guest.Gender.FEMALE, "Mme"),
            (Guest.Gender.MALE, "M."),
            (Guest.Gender.OTHER, "Autre"),
        ]
