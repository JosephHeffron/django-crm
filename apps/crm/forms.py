from django import forms

from .models import Company, Contact


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            "name",
            "website",
            "phone",
            "industry",
            "notes",
            "is_active",
            "owner",
        ]


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "title",
            "company",
            "notes",
            "is_active",
            "owner",
        ]
