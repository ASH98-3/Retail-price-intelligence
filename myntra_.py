from selenium import webdriver
from selenium.webdriver.common.by import By
import urllib.parse
import pandas as pd
from datetime import datetime
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

MAX_PAGES = 3          
MIN_PRODUCTS = 100 
WAIT_TIME = 5 
driver = webdriver.Chrome()
wait = WebDriverWait(driver, WAIT_TIME)

categories = {
    "sneakers": "https://www.myntra.com/sneakers",
    "tshirts": "https://www.myntra.com/tshirts",
    "jeans": "https://www.myntra.com/jeans"
}

def get_brands_from_filter(category_url):
    driver.get(category_url)

    # wait for page
    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "brand-more")))

    # click "+ more"
    driver.find_element(By.CLASS_NAME, "brand-more").click()

    # wait for popup
    panel = wait.until(
        EC.presence_of_element_located((By.CLASS_NAME, "FilterDirectory-panel"))
    )

    # scroll inside popup
    for _ in range(15):
        driver.execute_script(
            "arguments[0].scrollTop = arguments[0].scrollHeight", panel
        )

    brands = driver.find_elements(
        By.CSS_SELECTOR,
        ".FilterDirectory-panel label.common-customCheckbox"
    )

    brand_list = []

    for b in brands:
        text = b.text.strip()

        if "(" in text:
            name = text.split("(")[0].strip()
            count = int(text.split("(")[1].replace(")", "").strip())

            if count > MIN_PRODUCTS:
                brand_list.append((name, count))

    return brand_list

def scrape_page():
    wait.until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.product-base"))
    )

    products = driver.find_elements(By.CSS_SELECTOR, "li.product-base")

    data = []
    for p in products:
        try:
            brand = p.find_element(By.CLASS_NAME, "product-brand").text
            name = p.find_element(By.CLASS_NAME, "product-product").text
            price = p.find_element(By.CLASS_NAME, "product-discountedPrice").text

            try:
                original_price = p.find_element(By.CLASS_NAME, "product-strike").text
            except:
                original_price = None

            try:
                discount = p.find_element(By.CLASS_NAME, "product-discountPercentage").text
            except:
                discount = None

            try:
                rating_block = p.find_element(By.CLASS_NAME, "product-ratingsContainer").text
                
                if "|" in rating_block:
                    rating, rating_count = rating_block.split("|")
                    rating = rating.strip()
                    rating_count = rating_count.strip()
                else:
                    rating = rating_block
                    rating_count = None
            except:
                rating = None
                rating_count = None

            link = p.find_element(By.TAG_NAME, "a").get_attribute("href")

            data.append({
                "brand": brand,
                "product_name": name,
                "price": price,
                "original_price": original_price,
                "discount": discount,
                "rating": rating,
                "rating_count": rating_count,
                "product_link": link
            })

        except:
            continue

    return data

# ---------- MAIN ----------
all_data = []

for category_name, base_url in categories.items():
    print(f"\n===== CATEGORY: {category_name} =====")

    brand_list = get_brands_from_filter(base_url)
    print(f"Brands selected: {len(brand_list)}")
    # brand_list = brand_list[:3]

    for brand_name, count in brand_list:
        print(f"🔹 {brand_name}")

        page = 1

        while page <= MAX_PAGES:
            url = base_url + "?f=Brand%3A" + urllib.parse.quote(brand_name) + f"&p={page}"

            driver.get(url)

            try:
                page_data = scrape_page()
            except:
                print(f"⚠️ Failed page {page}")
                break

            if not page_data:
                print(f"✔ Finished early: {brand_name}")
                break

            for item in page_data:
                item["category"] = category_name
                item["search_brand"] = brand_name

            all_data.extend(page_data)

            print(f"{category_name} | {brand_name} | Page {page} → {len(page_data)}")

            page += 1

df = pd.DataFrame(all_data)

today = datetime.now().strftime("%Y-%m-%d")
df["scrape_date"] = today

df.drop_duplicates(subset="product_link", inplace=True)

df.to_csv(f"myntra_raw_{today}.csv", index=False)

print("\n DONE")
print("Total products:", len(df))