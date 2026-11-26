from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class ServiceExportModalTests(TestCase):
    def test_services_export_modal_renders_pdf_and_excel_buttons(self):
        admin = get_user_model().objects.create_user(
            username="service-export-modal-admin",
            password="test-password",
            usertype="HeadOffice",
        )
        self.client.force_login(admin)

        response = self.client.get(reverse("web:all_sections"))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('id="downloadPdfBtn"', html)
        self.assertIn('id="downloadExcelBtn"', html)
        self.assertRegex(
            html,
            r'<button type="button" id="downloadExcelBtn" class="btn btn-success"[^>]*>',
        )
        self.assertNotRegex(
            html,
            r'<button[^>]*id="downloadExcelBtn"[^>]*(?:hidden|d-none|disabled|display\s*:\s*none)',
        )
        self.assertLess(html.index('id="downloadPdfBtn"'), html.index('id="downloadExcelBtn"'))
