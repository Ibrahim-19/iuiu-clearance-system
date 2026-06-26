"""PDF Clearance Certificate generator with embedded QR-code fraud protection.

Uses ReportLab for PDF layout and `qrcode` to generate a verification QR
code that links back to a public verification page on this system, so an
employer can scan it and confirm the certificate is genuine.
"""
import io
import os
import secrets

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


BRAND_GREEN = HexColor("#146C43")
BRAND_GOLD = HexColor("#C9A227")
TEXT_DARK = HexColor("#1A1A1A")
TEXT_GREY = HexColor("#555555")


def _make_qr_image(verify_url):
    qr = qrcode.QRCode(version=2, box_size=8, border=2)
    qr.add_data(verify_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def generate_certificate_pdf_bytes(student, clearance_request, departments_status, verify_url):
    """Render the clearance certificate PDF entirely in memory and return
    the raw PDF bytes. Keeping this filesystem-free lets the caller either
    write it to local disk (dev) or upload it straight to Cloudinary
    (production) without ever needing a writable path on Render's
    ephemeral filesystem.

    departments_status: list of dicts {name, status, approved_by, approved_at}
    """
    buffer = io.BytesIO()
    width, height = A4
    c = canvas.Canvas(buffer, pagesize=A4)

    # Decorative border
    c.setStrokeColor(BRAND_GREEN)
    c.setLineWidth(3)
    c.rect(15 * mm, 15 * mm, width - 30 * mm, height - 30 * mm)
    c.setStrokeColor(BRAND_GOLD)
    c.setLineWidth(1)
    c.rect(18 * mm, 18 * mm, width - 36 * mm, height - 36 * mm)

    # Header
    c.setFillColor(BRAND_GREEN)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2, height - 35 * mm, "ISLAMIC UNIVERSITY IN UGANDA")
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, height - 42 * mm, "ARUA CAMPUS")
    c.setFillColor(TEXT_GREY)
    c.setFont("Helvetica", 11)
    c.drawCentredString(width / 2, height - 49 * mm, "Online Graduation Clearance System")

    c.setStrokeColor(BRAND_GOLD)
    c.setLineWidth(1.2)
    c.line(width / 2 - 60 * mm, height - 53 * mm, width / 2 + 60 * mm, height - 53 * mm)

    # Title
    c.setFillColor(TEXT_DARK)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(width / 2, height - 68 * mm, "GRADUATION CLEARANCE FORM")

    # Body text
    c.setFont("Helvetica", 12)
    c.setFillColor(TEXT_DARK)
    body_y = height - 85 * mm
    c.drawCentredString(width / 2, body_y, "This is to certify that")

    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(BRAND_GREEN)
    c.drawCentredString(width / 2, body_y - 9 * mm, student.name.upper())

    c.setFont("Helvetica", 12)
    c.setFillColor(TEXT_DARK)
    c.drawCentredString(width / 2, body_y - 17 * mm, f"Registration Number: {student.reg_number}")
    course_label = student.course_name or student.course_type
    c.drawCentredString(width / 2, body_y - 24 * mm, f"Programme: {course_label}")
    c.drawCentredString(
        width / 2, body_y - 31 * mm,
        "has satisfied all graduation clearance requirements of the following offices:"
    )

    # Departments table
    table_top = body_y - 42 * mm
    row_h = 8 * mm
    col1_x = 30 * mm
    col2_x = width - 60 * mm

    c.setFont("Helvetica-Bold", 10.5)
    c.setFillColor(BRAND_GREEN)
    c.drawString(col1_x, table_top, "DEPARTMENT / OFFICE")
    c.drawString(col2_x, table_top, "STATUS")
    c.line(col1_x, table_top - 2 * mm, width - 30 * mm, table_top - 2 * mm)

    c.setFont("Helvetica", 10.5)
    y = table_top - row_h
    for dept in departments_status:
        c.setFillColor(TEXT_DARK)
        c.drawString(col1_x, y, dept["name"])
        c.setFillColor(HexColor("#1E7B34"))
        c.drawString(col2_x, y, "APPROVED")
        y -= row_h

    # Tracking + dates
    c.setFillColor(TEXT_GREY)
    c.setFont("Helvetica", 9.5)
    cleared_date = clearance_request.fully_cleared_at.strftime("%d %B %Y") if clearance_request.fully_cleared_at else "-"
    c.drawString(30 * mm, y - 6 * mm, f"Tracking Reference: {clearance_request.tracking_code}")
    c.drawString(30 * mm, y - 12 * mm, f"Date Fully Cleared: {cleared_date}")
    c.drawString(30 * mm, y - 18 * mm, f"Verification Code: {clearance_request.verification_code}")

    # QR code (fraud protection)
    qr_buf = _make_qr_image(verify_url)
    qr_img = ImageReader(qr_buf)
    qr_size = 28 * mm
    qr_x = width - 30 * mm - qr_size
    qr_y = 25 * mm
    c.drawImage(qr_img, qr_x, qr_y, width=qr_size, height=qr_size, mask="auto")
    c.setFont("Helvetica", 7.5)
    c.setFillColor(TEXT_GREY)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 5, "Scan to verify authenticity")

    # Signature line
    c.setStrokeColor(TEXT_DARK)
    c.line(30 * mm, 35 * mm, 90 * mm, 35 * mm)
    c.setFont("Helvetica", 9.5)
    c.setFillColor(TEXT_DARK)
    c.drawString(30 * mm, 30 * mm, "Academic Registrar")

    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(TEXT_GREY)
    c.drawCentredString(
        width / 2, 18 * mm,
        "This certificate was generated electronically and is independently verifiable via the QR code above."
    )

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


def make_verification_code():
    return secrets.token_urlsafe(16)
