from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import urllib.parse
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

MAX_PAGES = 3
MIN_PRODUCTS = 100
WAIT_TIME = 3  # Reduced from 5
NUM_WORKERS = 3  # Parallel browser instances

categories = {
    #"sneakers": "https://www.myntra.com/sneakers",
    #"tshirts": "https://www.myntra.com/tshirts",
     #"jeans": "https://www.myntra.com/jeans"
}

def get_brands_from_filter(category_url):
    driver = webdriver.Chrome()
    wait = WebDriverWait(driver, WAIT_TIME)
    try:
        driver.get(category_url)
        
        # Combined wait - only wait for the actual element we need
        try:
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "brand-more")))
            driver.find_element(By.CLASS_NAME, "brand-more").click()
        except:
            # Fallback if brand-more doesn't exist
            driver.close()
            return []
        
        # Wait for panel
        panel = wait.until(
            EC.presence_of_element_located((By.CLASS_NAME, "FilterDirectory-panel"))
        )
        
        # Scroll to load all brands (10 scrolls instead of 15)
        for _ in range(10):
            driver.execute_script(
                "arguments[0].scrollTop = arguments[0].scrollHeight", panel
            )
            time.sleep(0.1)  # Minimal sleep
        
        brands = driver.find_elements(
            By.CSS_SELECTOR, ".FilterDirectory-panel label.common-customCheckbox"
        )
        
        brand_list = []
        for b in brands:
            try:
                text = b.text.strip()
                if "(" in text:
                    name = text.split("(")[0].strip()
                    count = int(text.split("(")[1].replace(")", "").strip())
                    if count > MIN_PRODUCTS:
                        brand_list.append((name, count))
            except:
                continue
        
        return brand_list
    finally:
        driver.quit()

def scrape_page(url):
    """Scrape a single page - returns data or empty list if fails"""
    driver = webdriver.Chrome()
    wait = WebDriverWait(driver, WAIT_TIME)
    try:
        driver.get(url)
        
        # Wait for products with shorter timeout
        try:
            wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.product-base"))
            )
        except:
            return []
        
        products = driver.find_elements(By.CSS_SELECTOR, "li.product-base")
        data = []
        
        for p in products:
            try:
                brand = p.find_element(By.CLASS_NAME, "product-brand").text
                name = p.find_element(By.CLASS_NAME, "product-product").text
                price = p.find_element(By.CLASS_NAME, "product-discountedPrice").text
                
                # Use try-except for optional fields instead of separate waits
                original_price = None
                discount = None
                rating = None
                rating_count = None
                
                try:
                    original_price = p.find_element(By.CLASS_NAME, "product-strike").text
                except:
                    pass
                
                try:
                    discount = p.find_element(By.CLASS_NAME, "product-discountPercentage").text
                except:
                    pass
                
                try:
                    rating_block = p.find_element(By.CLASS_NAME, "product-ratingsContainer").text
                    if "|" in rating_block:
                        rating, rating_count = rating_block.split("|")
                        rating = rating.strip()
                        rating_count = rating_count.strip()
                    else:
                        rating = rating_block
                except:
                    pass
                
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
    except:
        return []
    finally:
        driver.quit()

def scrape_brand(category_name, base_url, brand_name, brand_count):
    """Scrape all pages for a single brand - called by thread pool"""
    all_brand_data = []
    
    for page in range(1, MAX_PAGES + 1):
        url = base_url + "?f=Brand%3A" + urllib.parse.quote(brand_name) + f"&p={page}"
        page_data = scrape_page(url)
        
        if not page_data:
            # No more products, stop pagination
            break
        
        for item in page_data:
            item["category"] = category_name
            item["search_brand"] = brand_name
        
        all_brand_data.extend(page_data)
        print(f"{category_name} | {brand_name} | Page {page} → {len(page_data)} products")
    
    return all_brand_data

# ---------- MAIN ----------
all_data = []

for category_name, base_url in categories.items():
    print(f"\n===== CATEGORY: {category_name} =====")
    
    # Get brands (single-threaded as it needs one driver)
    brand_list = get_brands_from_filter(base_url)
    print(f"Brands selected: {len(brand_list)}\n")
    
    # Parallel execution for brand scraping
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = []
        
        # Submit all brand tasks
        for brand_name, count in brand_list:
            future = executor.submit(
                scrape_brand, category_name, base_url, brand_name, count
            )
            futures.append(future)
        
        # Collect results as they complete
        for future in as_completed(futures):
            try:
                brand_data = future.result()
                all_data.extend(brand_data)
            except Exception as e:
                print(f"Error scraping brand: {e}")

# Save results
df = pd.DataFrame(all_data)
today = datetime.now().strftime("%Y-%m-%d")
df["scrape_date"] = today
df.drop_duplicates(subset="product_link", inplace=True)
df.to_csv(f"myntra_raw_{today}.csv", index=False)

print(f"\n✅ DONE - Total products: {len(df)}")
