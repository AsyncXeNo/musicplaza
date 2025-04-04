from __future__ import annotations

import time
import asyncio

from apify import Actor, Request
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        start_urls = actor_input.get('urls')

        if not start_urls:
            Actor.log.info('No start URLs specified in actor input, exiting...')
            await Actor.exit()

        request_queue = await Actor.open_request_queue()

        for start_url in start_urls:
            url = start_url.get('url')
            Actor.log.info(f'Enqueuing {url} ...')
            new_request = Request.from_url(url)
            await request_queue.add_request(new_request)

        Actor.log.info('Launching Chrome WebDriver...')
        chrome_options = ChromeOptions()

        # if Actor.config.headless:
        #     chrome_options.add_argument('--headless')

        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        driver = webdriver.Chrome(options=chrome_options)

        data = []

        while request := await request_queue.fetch_next_request():
            url = request.url

            Actor.log.info(f'Scraping {url} ...')

            try:
                await asyncio.to_thread(driver.get, url)

                title = driver.find_element(By.CSS_SELECTOR, '.product-title').get_attribute('innerText').strip()

                price = float(driver.find_element(By.CSS_SELECTOR, '.main-product-price .price').get_attribute('innerText').replace('$', '').replace('USD', '').replace(',', '').strip())

                main_image = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, '#media_product-template--23844484612380__main .media-slide.is-active img')
                    )
                ).get_attribute('srcset').split(' ')[0].replace('//', 'https://')

                image_divs = driver.find_elements(By.CSS_SELECTOR, '#media_product-template--23844484612380__main .media-slide img')
                images = [image.get_attribute('srcset').split(' ')[0].replace('//', 'https://') for image in image_divs]

                description = driver.find_element(By.CSS_SELECTOR, '.content-0')

                driver.execute_script("arguments[0].scrollIntoView();", description)
                time.sleep(0.6)

                description = description.get_attribute('innerText').strip()

                description_image_tags = driver.find_elements(By.CSS_SELECTOR, '.content-0 img')
                description_images = [image.get_attribute('src') for image in description_image_tags]

                try:
                    variant_select_element = driver.find_element(By.CSS_SELECTOR, '.select select')
                    options = variant_select_element.find_elements(By.TAG_NAME, 'option')
                    variants_exist = True
                except Exception:
                    variants_exist = False
                
                variant_info = []
                
                if variants_exist:
                    for index in range(len(options)):

                        variant_select_element = driver.find_element(By.CSS_SELECTOR, '.select select')
                        variant_name = variant_select_element.find_elements(By.TAG_NAME, 'option')[index].get_attribute('innerText').strip()
                        variant_select = Select(variant_select_element)

                        variant_select.select_by_index(index)

                        time.sleep(0.5)

                        variant_info.append({
                            'name': variant_name,
                            'price': float(driver.find_element(By.CSS_SELECTOR, '.main-product-price .price').get_attribute('innerText').replace('$', '').replace('USD', '').replace(',', '').strip()),
                            'image': driver.find_element(By.CSS_SELECTOR, '#media_product-template--23844484612380__main .media-slide.is-active img').get_attribute('srcset').split(' ')[0].replace('//', 'https://')
                        })


                data.append({
                    'url': url,
                    'title': title,
                    'collections': [],
                    'price': price,
                    'main_image': main_image,
                    'images': images,
                    'description_images': description_images,
                    'description': description,
                    'variants': variant_info
                })

            except Exception:
                Actor.log.exception(f'Cannot extract data from {url}.')

            finally:
                await request_queue.mark_request_as_handled(request)

        driver.quit()

        await Actor.push_data({
            'urls': data
        })