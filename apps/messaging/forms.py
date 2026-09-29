from django import forms

from .models import Message

MAX_MESSAGE_LENGTH = 4000


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ["body"]
        labels = {"body": "Message"}
        widgets = {
            "body": forms.Textarea(
                attrs={"rows": 2, "maxlength": MAX_MESSAGE_LENGTH, "placeholder": "Write a message"}
            )
        }

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if not body:
            raise forms.ValidationError("Write something first.")
        if len(body) > MAX_MESSAGE_LENGTH:
            raise forms.ValidationError(f"Keep it under {MAX_MESSAGE_LENGTH} characters.")
        return body
