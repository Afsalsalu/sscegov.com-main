from django.urls import path

from .views import exam_qualified_user


app_name = "integrations"

urlpatterns = [
    path(
        "sscentrepreneur/exam-qualified-user/",
        exam_qualified_user,
        name="exam-qualified-user",
    ),
]
