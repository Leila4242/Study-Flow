from PIL import Image, ImageChops

img_path = r'C:\Users\aysu\.gemini\antigravity\brain\657c117d-3d00-458e-a8c3-bbf2cc46747a\study_flow_logo_1784172796244.png'
dest_path = r'c:\Users\aysu\Unec_FutureDev_Camp_Final_Project\static\images\logo.png'

try:
    img = Image.open(img_path)
    img_rgb = img.convert("RGB")
    
    bg = Image.new("RGB", img_rgb.size, (255, 255, 255))
    diff = ImageChops.difference(img_rgb, bg)
    bbox = diff.getbbox()
    
    if bbox:
        # The bounding box might include the text as well if the original had text.
        # But wait! If the original had text, the bounding box of non-white pixels will include the text.
        # If the image is like [Icon]   [Text], we might need to just crop the left half, or we can just run crop.
        # Let's crop it into squares from the left to isolate the icon.
        # Actually, let's just use the crop coordinates based on the image aspect ratio.
        # Assuming the icon is on the left and is roughly square.
        
        left, upper, right, lower = bbox
        
        # If width is much larger than height, it probably has text on the right.
        width = right - left
        height = lower - upper
        if width > height * 1.5:
            # It has text, crop to a square from the left
            right = left + height
            
        cropped_img = img.crop((left, upper, right, lower))
        
        # Make white transparent
        cropped_img = cropped_img.convert("RGBA")
        datas = cropped_img.getdata()
        new_data = []
        for item in datas:
            if item[0] > 240 and item[1] > 240 and item[2] > 240:
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append(item)
        cropped_img.putdata(new_data)
        
        cropped_img.save(dest_path, "PNG")
        print("Successfully cropped and made transparent.")
    else:
        print("Could not find bounding box.")
except Exception as e:
    print(f"Error: {e}")
