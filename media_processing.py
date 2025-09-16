"""
Image/Video Processing Module (Inactive Stub)
---------------------------------------------
This module is a placeholder for future image/video handling.
Right now, all functions are no-ops that log usage.

Intended Features (future):
- Accept image uploads from user tasks (photo proof).
- Perform anonymization (blur faces, crop regions).
- Generate composite progress trackers.
- Handle video compression or splitting.
"""

import logging

def process_image(file_path: str, options: dict = None):
    logging.info(f"[MEDIA] Pretend processing image {file_path} with options={options}")
    return file_path  # just return original path

def process_video(file_path: str, options: dict = None):
    logging.info(f"[MEDIA] Pretend processing video {file_path} with options={options}")
    return file_path

def anonymize_image(file_path: str):
    logging.info(f"[MEDIA] Pretend anonymizing image {file_path}")
    return file_path

def generate_progress_contact_sheet(image_paths: list, output_path: str):
    logging.info(f"[MEDIA] Pretend generating contact sheet at {output_path} with {len(image_paths)} images")
    return output_path
