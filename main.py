import cv2
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Step 1: Read the image
image = cv2.imread("samples/sample_invoice.jpg")

# Step 2: Converting to grayscale
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# Step 3: Run OCR - extracts the text from image
text = pytesseract.image_to_string(gray)

# Step 4: Output
print("Extracted Text:\n")
print(text)
