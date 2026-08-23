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
    age_category = forms.ChoiceField(label="Tranche d’âge", choices=[])

    def __init__(self, *args, **kwargs):
        from guests.models import Guest

        super().__init__(*args, **kwargs)
        self.fields["gender"].choices = [
            (Guest.Gender.FEMALE, "Mme"),
            (Guest.Gender.MALE, "M."),
            (Guest.Gender.OTHER, "Autre"),
        ]
        self.fields["age_category"].choices = [
            ("", "Sélectionnez une tranche d’âge"),
            *Guest.AgeCategory.choices,
        ]


class RSVPForm(forms.Form):
    status = forms.ChoiceField(
        label="Serez-vous présent(e) ?",
        choices=[],
        widget=forms.RadioSelect,
    )
    age_category = forms.ChoiceField(label="Votre tranche d’âge", choices=[])

    def __init__(self, *args, guest, **kwargs):
        from guests.models import Guest

        super().__init__(*args, **kwargs)
        self.guest = guest
        self.fields["status"].choices = [
            (Guest.RSVPStatus.ATTENDING, "Oui, avec joie"),
            (Guest.RSVPStatus.NOT_ATTENDING, "Non, je ne pourrai pas être présent(e)"),
        ]
        self.fields["age_category"].choices = [
            ("", "Sélectionnez une tranche d’âge"),
            *Guest.AgeCategory.choices,
        ]
        self.initial["age_category"] = guest.age_category
        self.initial["status"] = (
            guest.rsvp_status if guest.rsvp_status != Guest.RSVPStatus.PENDING else ""
        )
        for invitation in guest.event_invitations.select_related("event").filter(
            event__is_active=True,
            event__requires_rsvp=True,
            is_eligible=True,
        ):
            field_name = f"event_{invitation.event.code}"
            self.fields[field_name] = forms.ChoiceField(
                label=invitation.event.name,
                choices=[
                    (Guest.RSVPStatus.ATTENDING, "Oui"),
                    (Guest.RSVPStatus.NOT_ATTENDING, "Non"),
                ],
                widget=forms.RadioSelect,
                required=False,
            )
            if invitation.attendance_status != Guest.RSVPStatus.PENDING:
                self.initial[field_name] = invitation.attendance_status

    def clean(self):
        from guests.models import Guest

        cleaned_data = super().clean()
        if cleaned_data.get("status") == Guest.RSVPStatus.ATTENDING:
            for field_name, field in self.fields.items():
                if field_name.startswith("event_") and not cleaned_data.get(field_name):
                    self.add_error(field_name, "Choisissez une réponse pour cet événement.")
        return cleaned_data

    def event_responses(self):
        return {
            field_name.removeprefix("event_"): value
            for field_name, value in self.cleaned_data.items()
            if field_name.startswith("event_") and value
        }


class GuestEmailForm(forms.Form):
    email = forms.EmailField(label="Votre adresse email", max_length=254)


class CompanionAttendanceForm(forms.Form):
    attendance_mode = forms.ChoiceField(
        label="Disponibilités",
        choices=[],
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, companion, **kwargs):
        from guests.models import Guest
        from guests.services.capacity import attendance_is_open

        super().__init__(*args, **kwargs)
        self.companion = companion
        city_hall = companion.event_invitations.select_related("event").filter(
            event__code="city_hall",
            event__is_active=True,
            is_eligible=False,
        ).first()
        owner_city_hall_eligible = bool(
            city_hall
            and companion.invitation_owner.event_invitations.filter(
                event=city_hall.event,
                is_eligible=True,
            ).exists()
        )
        self.city_hall_restricted = owner_city_hall_eligible
        self.fields["attendance_mode"].choices = Guest.AttendanceMode.choices
        self.initial["attendance_mode"] = companion.attendance_mode
        self.has_open_events = False
        for invitation in companion.event_invitations.select_related("event").filter(
            event__is_active=True,
            event__requires_rsvp=True,
            is_eligible=True,
        ):
            name = f"event_{invitation.event.code}"
            is_open = attendance_is_open(invitation.event)
            self.has_open_events = self.has_open_events or is_open
            self.fields[name] = forms.ChoiceField(
                label=invitation.event.name,
                choices=[
                    (Guest.RSVPStatus.ATTENDING, "Oui"),
                    (Guest.RSVPStatus.NOT_ATTENDING, "Non"),
                ],
                widget=forms.RadioSelect,
                required=False,
                disabled=not is_open,
            )
            if invitation.attendance_status != Guest.RSVPStatus.PENDING:
                self.initial[name] = invitation.attendance_status
        self.fields["attendance_mode"].disabled = not self.has_open_events

    def clean(self):
        from guests.models import Guest

        data = super().clean()
        if data.get("attendance_mode") == Guest.AttendanceMode.CUSTOM:
            for name in self.fields:
                if name.startswith("event_") and not data.get(name):
                    self.add_error(name, "Choisissez une réponse pour cet événement.")
        return data

    def event_responses(self):
        return {
            name.removeprefix("event_"): value
            for name, value in self.cleaned_data.items()
            if name.startswith("event_") and value
        }


class GuestEventInvitationAdminForm(forms.ModelForm):
    class Meta:
        from guests.models import GuestEventInvitation

        model = GuestEventInvitation
        fields = "__all__"

    def clean(self):
        from guests.models import Guest

        data = super().clean()
        if data.get("is_eligible") is False:
            data["attendance_status"] = Guest.RSVPStatus.NOT_ATTENDING
            data["response_source"] = Guest.RSVPSource.ADMIN
        return data

    def save(self, commit=True):
        from guests.models import GuestEventInvitation

        instance = super().save(commit=False)
        if "is_eligible" in self.changed_data:
            instance.eligibility_source = GuestEventInvitation.EligibilitySource.ADMIN
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class AccessRecoveryForm(forms.Form):
    email = forms.EmailField(label="Adresse email vérifiée", max_length=254)
