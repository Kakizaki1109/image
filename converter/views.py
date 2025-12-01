import io
import os
import re
import zipfile
from datetime import datetime
from PIL import Image
from django.http import HttpResponse
from django.shortcuts import render


RESOLUTIONS = {
    'hd': (1280, 720),
    'fullhd': (1920, 1080),
}

# Max file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024

# Allowed MIME types
ALLOWED_CONTENT_TYPES = {'image/jpeg', 'image/png'}


def sanitize_filename(filename):
    """
    Sanitize filename to prevent path traversal and other security issues.
    Only allow alphanumeric characters, hyphens, underscores, and dots.
    """
    # Get just the base name (no directory components)
    basename = os.path.basename(filename)
    # Remove any potentially dangerous characters
    sanitized = re.sub(r'[^\w\-.]', '_', basename)
    # Prevent empty or dot-only filenames
    if not sanitized or sanitized.startswith('.'):
        sanitized = 'image' + sanitized
    return sanitized


def convert_image(image_file, target_width, target_height):
    """
    Convert an image to the target resolution while preserving aspect ratio.
    Uses letterboxing (padding) to reach exact target size.
    PNG stays PNG with transparency; JPEG or other becomes JPEG with black padding.
    """
    img = Image.open(image_file)
    original_format = img.format

    # Determine if PNG (for transparency support)
    is_png = original_format == 'PNG'

    # Calculate aspect ratio preserving dimensions
    original_width, original_height = img.size
    ratio = min(target_width / original_width, target_height / original_height)
    new_width = int(original_width * ratio)
    new_height = int(original_height * ratio)

    # Resize image maintaining aspect ratio
    resized_img = img.resize((new_width, new_height), Image.LANCZOS)

    if is_png:
        # Create transparent background for PNG
        result = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
        # Convert resized image to RGBA if needed
        if resized_img.mode != 'RGBA':
            resized_img = resized_img.convert('RGBA')
    else:
        # Create black background for JPEG
        result = Image.new('RGB', (target_width, target_height), (0, 0, 0))
        # Convert resized image to RGB if needed
        if resized_img.mode != 'RGB':
            resized_img = resized_img.convert('RGB')

    # Calculate position to center the image
    x_offset = (target_width - new_width) // 2
    y_offset = (target_height - new_height) // 2

    # Paste the resized image onto the background
    result.paste(resized_img, (x_offset, y_offset))

    # Save to buffer
    buffer = io.BytesIO()
    if is_png:
        result.save(buffer, format='PNG', optimize=True)
        output_format = 'png'
    else:
        result.save(buffer, format='JPEG', quality=92)
        output_format = 'jpeg'

    buffer.seek(0)
    return buffer, output_format


def index(request):
    """Display the upload form."""
    return render(request, 'converter/index.html')


def convert(request):
    """Handle file uploads and conversion."""
    if request.method != 'POST':
        return render(request, 'converter/index.html')

    files = request.FILES.getlist('images')
    resolution = request.POST.get('resolution', 'hd')

    if not files:
        return render(request, 'converter/index.html', {'error': 'No files uploaded'})

    if resolution not in RESOLUTIONS:
        return render(request, 'converter/index.html', {'error': 'Invalid resolution'})

    target_width, target_height = RESOLUTIONS[resolution]

    # Create ZIP file in memory
    zip_buffer = io.BytesIO()
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    failed_files = []
    used_filenames = set()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for uploaded_file in files:
            # Validate file size
            if uploaded_file.size > MAX_FILE_SIZE:
                failed_files.append(f"{uploaded_file.name} (file too large)")
                continue

            # Validate content type
            if uploaded_file.content_type not in ALLOWED_CONTENT_TYPES:
                failed_files.append(f"{uploaded_file.name} (unsupported format)")
                continue

            # Sanitize and get original filename without extension
            sanitized_name = sanitize_filename(uploaded_file.name)
            original_name = os.path.splitext(sanitized_name)[0]

            try:
                converted_buffer, output_format = convert_image(
                    uploaded_file, target_width, target_height
                )

                # Create unique output filename to avoid collisions
                base_filename = f"{original_name}.{output_format}"
                output_filename = base_filename
                counter = 1
                while output_filename in used_filenames:
                    output_filename = f"{original_name}_{counter}.{output_format}"
                    counter += 1
                used_filenames.add(output_filename)

                # Add to ZIP
                zip_file.writestr(output_filename, converted_buffer.read())
            except Exception:
                failed_files.append(f"{uploaded_file.name} (conversion failed)")
                continue

    zip_buffer.seek(0)

    # Check if any files were successfully converted
    if not used_filenames:
        error_msg = 'No files could be converted.'
        if failed_files:
            error_msg += f' Failed: {", ".join(failed_files)}'
        return render(request, 'converter/index.html', {'error': error_msg})

    # Create response with ZIP file
    resolution_label = 'hd' if resolution == 'hd' else 'fullhd'
    zip_filename = f"converted-{resolution_label}-{timestamp}.zip"

    response = HttpResponse(zip_buffer.read(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'

    return response
