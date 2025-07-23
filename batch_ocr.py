import os
import cv2                      #OpenCV for image reading and processing
import pytesseract              #Python wrapper for Tesseract OCR

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

samples_folder = "samples" 

for filename in os.listdir(samples_folder):
    if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
        file_path = os.path.join(samples_folder, filename)
        print(f"Processing: {filename}")

        # Step 1: Read the image
        image = cv2.imread(file_path)
        if image is None:
            print(f"Warning: {filename} could not be loaded. Skipping.")
            continue

        # Step 2: Converting to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR) #resizing

        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]  #Binarizing (thresholding to black/white)

        custom_config = r'--oem 3 --psm 6' #Assumes a single uniform block of text



        # Step 3: Run OCR - extracts the text from image
        text = pytesseract.image_to_string(thresh, config=custom_config)

        # Step 4: Saveing the output to a .txt file
        out_filename = os.path.splitext(filename)[0]+".txt"
        out_path = os.path.join(samples_folder, out_filename)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)

        print(f"Saved OCR result to: {out_filename}")

print("\nBatch OCR complete!")