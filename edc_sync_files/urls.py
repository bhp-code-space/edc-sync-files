from django.urls import path
from django.views.generic.base import RedirectView

from .admin_site import edc_sync_files_admin

app_name = 'edc_sync_files'

urlpatterns = [
    path('admin/', edc_sync_files_admin.urls),
    path('', RedirectView.as_view(url='admin/')),
]
