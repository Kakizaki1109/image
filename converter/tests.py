import io
import zipfile
from PIL import Image
from django.test import TestCase, Client
from django.core.files.uploadedfile import SimpleUploadedFile
from converter.views import convert_image


class ConvertImageTestCase(TestCase):
    """Test cases for the convert_image function."""

    def create_png_image(self, width=100, height=100):
        """Create a test PNG image."""
        img = Image.new('RGBA', (width, height), (255, 0, 0, 128))
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer

    def create_jpeg_image(self, width=200, height=100):
        """Create a test JPEG image."""
        img = Image.new('RGB', (width, height), (0, 255, 0))
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        buffer.seek(0)
        return buffer

    def test_png_conversion_hd(self):
        """Test PNG conversion to HD resolution."""
        png_file = self.create_png_image()
        result_buffer, output_format = convert_image(png_file, 1280, 720)

        self.assertEqual(output_format, 'png')

        result_buffer.seek(0)
        result = Image.open(result_buffer)
        self.assertEqual(result.size, (1280, 720))
        self.assertEqual(result.mode, 'RGBA')

    def test_jpeg_conversion_hd(self):
        """Test JPEG conversion to HD resolution."""
        jpeg_file = self.create_jpeg_image()
        result_buffer, output_format = convert_image(jpeg_file, 1280, 720)

        self.assertEqual(output_format, 'jpeg')

        result_buffer.seek(0)
        result = Image.open(result_buffer)
        self.assertEqual(result.size, (1280, 720))
        self.assertEqual(result.mode, 'RGB')

    def test_png_conversion_fullhd(self):
        """Test PNG conversion to Full HD resolution."""
        png_file = self.create_png_image()
        result_buffer, output_format = convert_image(png_file, 1920, 1080)

        result_buffer.seek(0)
        result = Image.open(result_buffer)
        self.assertEqual(result.size, (1920, 1080))

    def test_aspect_ratio_preservation(self):
        """Test that aspect ratio is preserved (letterboxing)."""
        # Create a wide image (200x100)
        wide_image = self.create_jpeg_image(200, 100)
        result_buffer, _ = convert_image(wide_image, 1280, 720)

        result_buffer.seek(0)
        result = Image.open(result_buffer)
        self.assertEqual(result.size, (1280, 720))


class ConvertViewTestCase(TestCase):
    """Test cases for the convert view."""

    def setUp(self):
        self.client = Client()

    def create_png_bytes(self):
        """Create PNG image bytes."""
        img = Image.new('RGBA', (100, 100), (255, 0, 0, 128))
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer.read()

    def create_jpeg_bytes(self):
        """Create JPEG image bytes."""
        img = Image.new('RGB', (200, 100), (0, 255, 0))
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        buffer.seek(0)
        return buffer.read()

    def test_index_page(self):
        """Test that index page loads correctly."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Image Converter')

    def test_convert_multiple_files(self):
        """Test conversion of multiple files."""
        png_data = self.create_png_bytes()
        jpeg_data = self.create_jpeg_bytes()

        response = self.client.post('/convert/', {
            'images': [
                SimpleUploadedFile('test.png', png_data, content_type='image/png'),
                SimpleUploadedFile('test.jpg', jpeg_data, content_type='image/jpeg'),
            ],
            'resolution': 'hd'
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertIn('converted-hd-', response['Content-Disposition'])

        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            files = zf.namelist()
            self.assertIn('test.png', files)
            self.assertIn('test.jpeg', files)

    def test_convert_fullhd(self):
        """Test Full HD conversion."""
        png_data = self.create_png_bytes()

        response = self.client.post('/convert/', {
            'images': SimpleUploadedFile('test.png', png_data, content_type='image/png'),
            'resolution': 'fullhd'
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('converted-fullhd-', response['Content-Disposition'])

        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            with zf.open('test.png') as f:
                result = Image.open(f)
                self.assertEqual(result.size, (1920, 1080))

    def test_no_files_uploaded(self):
        """Test error when no files are uploaded."""
        response = self.client.post('/convert/', {
            'resolution': 'hd'
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No files uploaded')

    def test_invalid_resolution(self):
        """Test error when invalid resolution is provided."""
        png_data = self.create_png_bytes()

        response = self.client.post('/convert/', {
            'images': SimpleUploadedFile('test.png', png_data, content_type='image/png'),
            'resolution': 'invalid'
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid resolution')

