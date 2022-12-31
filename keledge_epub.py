# kelege ePub to HTML
# author: Wenbin FAN
# date: Jul. 2022
# mail: langzihuigu@qq.com
# 
import os
import re
import requests
import requests.utils
import json
import http.cookiejar as cookiejar
import sqlite3
import time
import numpy as np
from datetime import datetime
from tqdm import tqdm
import secrets # generate tokens for toc
import logging

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.keys import Keys # press page down
# from selenium.webdriver.common.proxy import Proxy, ProxyType

from bs4 import BeautifulSoup as bs
from lxml import etree
from urllib.parse import urlsplit
import urllib.request

class kezhi_epub():

    def __init__(self, url,
                 root=r'D:\keledgeEPub',
                 cookie_path='',
                 chrome_exe_path=r'D:\Program Files\Chrome\chromedriver.exe'):
        self.root = root
        self.cookie_path = cookie_path
        self.chrome_exe_path = chrome_exe_path

        self.init_logger()
        self.init_browser()

        self.url = url

        self.load_wait = 50

        self.image_folder_name = 'images'
        self.toc_html_name = 'TOC.html'
        self.main_html_name = 'main.html'
        self.index_html_name = 'index.html'

        self.toc_target = 'toc'
        self.main_target = 'text'

        return

    def init_logger(self):

        logFormatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s]  %(message)s")
        rootLogger = logging.getLogger()
        rootLogger.setLevel(logging.INFO)

        fileHandler = logging.FileHandler("{}".format(os.path.join(self.root,'fan.log')) )
        fileHandler.setFormatter(logFormatter)
        rootLogger.addHandler(fileHandler)

        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(logFormatter)
        rootLogger.addHandler(consoleHandler)

        return

    def init_browser(self):
        caps = DesiredCapabilities.CHROME
        caps['goog:loggingPrefs'] = {'performance': 'ALL'}
        options = Options()
        options.add_argument('--headless')
        # options.add_argument('--disable-gpu')
        options.add_argument("--window-size=1920,1080")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('lang=zh-CN,zh,zh-TW,en-US,en')
        options.add_argument(
            'user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36')
        options.add_argument("disable-blink-features=AutomationControlled")
        prefs = {"profile.managed_default_content_settings.images": 2} # disable images
        options.add_experimental_option("prefs", prefs)

        # prox = Proxy()
        # prox.proxy_type = ProxyType.MANUAL
        # prox.http_proxy = "127.0.0.1:80"

        # capabilities = webdriver.DesiredCapabilities.CHROME
        # prox.add_to_capabilities(capabilities)

        s = Service(self.chrome_exe_path)
        self.driver = webdriver.Chrome(
            ChromeDriverManager().install(),
            # service=s,
            desired_capabilities=caps,
            options=options)
        return

    def load_cookies(self, path):
        cj = cookiejar.MozillaCookieJar()
        cj.load(filename=path, ignore_discard=True, ignore_expires=True)

        for cookie in cj:
            cookie_dict = {'domain': cookie.domain, 'name': cookie.name, 'value': cookie.value, 'secure': cookie.secure}
            if cookie.expires:
                cookie_dict['expiry'] = cookie.expires
            if cookie.path_specified:
                cookie_dict['path'] = cookie.path
            self.driver.add_cookie(cookie_dict)
        return

    def download_image(self, url):
        big_img_url = urlsplit(url)._replace(query=None).geturl()
        big_img_url = str(big_img_url)
        img_name = big_img_url.split('/')[-1]
        # urllib.request.urlretrieve(big_img_url, os.path.join(self.img_folder, img_name))
        self.image_link_file.write(f'{big_img_url}\n  dir={self.img_folder}\n  out={img_name}\n')
        return img_name

    def parse_chapter(self, soup):

        # remove random characters
        for div in soup.find_all('span', {'class': 'random'}):
            div.decompose()

        # unwarp all span
        for s in soup.find_all('span'):
            s.unwrap()

        # download all image
        for img in soup('img'):
            img_url = img['data-src']
            img_name = self.download_image(img_url)
            img['src'] = f'./{self.image_folder_name}/{img_name}'
            # delete extra attributes
            del img['data-src']
            del img['isloaded']
            del img['Kezi_Zhang'] # test the attribute that does not exists

        # image in svg
        for img in soup('image'):
            img_url = img['xlink:href']
            img_name = self.download_image(img_url)
            img['xlink:href'] = f'./{self.image_folder_name}/{img_name}'

        # restore all href
        # "chap01.html#TAGTAGTAG" -> "#TAGTAGTAG"
        for xref in soup.find_all('a', attrs={'href': True}):
            if '#' in xref['href'] and 'http' not in xref['href']:
                xref['href'] = '#' + xref['href'].replace('#', '').replace('.', '')

        # get headings
        for heading in soup.find_all(re.compile("^h[1-6]$")) :
            level_text = heading.name
            try:
                hid = heading['id']
            except KeyError:
                logging.error(f'There is no ID for title: {level_text} - {heading.text}')
                hid = secrets.token_hex(16) # len = 32
            del heading['id']

            # internal wrap (... strange name XD
            toc_href = f'{hid}-TOC'
            head_text = heading.text
            heading.wrap(
                bs().new_tag('a', attrs=
                    {'href': f'{self.toc_html_name}#{toc_href}',
                     'target': self.toc_target,
                     'id': hid,
                     },
                             ))
            heading.parent.wrap(bs().new_tag(level_text))
            heading.unwrap()

            self.toc_html_file.write(
                f'<p class="{level_text}">'
                f'<a id="{toc_href}" href="{self.main_html_name}#{hid}" target="{self.main_target}">'
                f'{head_text}</a></p>\n'
            )
            self.toc_html_file.flush()

        for heading in soup.find_all('div', ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            level_text = heading.get('class')[0]
            try:
                hid = heading['id']
            except KeyError:
                logging.error(f'There is no ID for title: {level_text} - {heading.text}')
                hid = secrets.token_hex(16)  # len = 32
            del heading['id']
            heading.name = level_text

            # internal wrap (... strange name XD
            toc_href = f'{hid}-TOC'
            head_text = heading.text
            heading.wrap(
                bs().new_tag('a', attrs=
                {'href': f'{self.toc_html_name}#{toc_href}',
                 'target': self.toc_target,
                 'id': hid,
                 },
                             ))
            heading.parent.wrap(bs().new_tag(level_text))
            heading.unwrap()

            self.toc_html_file.write(
                f'<p class="{level_text}">'
                f'<a id="{toc_href}" href="{self.main_html_name}#{hid}" target="{self.main_target}">'
                f'{head_text}</a></p>\n'
            )
            self.toc_html_file.flush()


        self.main_html_file.write(str(soup))
        self.main_html_file.write('\n')
        self.main_html_file.flush()

        return

    def main(self):
        self.driver.get('https://www.keledge.com/login') # browse host before setting cookie
        # add cookies
        self.load_cookies(self.cookie_path)
        self.driver.get(self.url)
        element = WebDriverWait(self.driver, self.load_wait).until(
            EC.presence_of_element_located((By.CLASS_NAME, "epub-main"))
        )
        time.sleep(3) # sleep to wait the title loaded

        # get book title from html title
        title = self.driver.title
        self.title = re.sub(r'[^\w\-_\. ]', '_', title)

        # make book folder
        self.book_folder = os.path.join(self.root, self.title)
        if not os.path.exists(self.book_folder):
            os.makedirs(self.book_folder)
        self.img_folder = os.path.join(self.book_folder, self.image_folder_name)
        if not os.path.exists(self.img_folder):
            os.mkdir(self.img_folder)

        # index file
        index_html_file = open(os.path.join(self.book_folder, self.index_html_name), 'w', encoding='utf-8')
        index_html_contents = f'''<HTML>
<HEAD>
<TITLE>{self.title}</TITLE>
</HEAD>
<FRAMESET Cols="20%,*">
<FRAME SRC="{self.toc_html_name}" NAME="toc">
<FRAME SRC="{self.main_html_name}" NAME="text">
</FRAMESET>
</HTML>'''
        index_html_file.write(index_html_contents)
        index_html_file.close()

        # toc html file
        self.toc_html_file = open(os.path.join(self.book_folder, self.toc_html_name), 'w', encoding='utf-8')
        toc_html_contents = '''<html>
<head>
<title>TOC</title>
<link type="text/css" rel="stylesheet" href="../localEpubReader.css">
<link type="text/css" rel="stylesheet" href="localEpubReader.css">
</head>
'''
        self.toc_html_file.write(toc_html_contents)

        html_path = os.path.join(self.book_folder, self.main_html_name)
        self.main_html_file = open(html_path, 'w', encoding='utf-8')
        # write html basics: head, title, css
        self.main_html_file.write('<html>\n<head>\n<title>Main text</title>\n')
        self.main_html_file.write('<link type="text/css" rel="stylesheet" href="../localEpubReader.css">\n')
        self.main_html_file.write('<link type="text/css" rel="stylesheet" href="localEpubReader.css">\n')
        self.main_html_file.write('</head>\n')
        self.main_html_file.write('<body>\n<div class="epub-main">\n')

        # # turn off "guide" mask on the whole screen | 关闭覆盖在整个页面上的导航
        # self.driver.find_element(By.XPATH, '//*[@id="epub-reader"]/div[3]/div/div/ul/li[11]/div').click()

        # a file that stores all image links. we will download all images after grabbing the main text
        # the format is aria2c. below is the format.
        # 1 | <link>
        # 2 |   dir=<path>
        # 3 |   out=<file name>
        # 4 | <link 2>
        # 5 |   dir=<...>
        # ...
        self.image_link_file = open(os.path.join(self.book_folder, 'image.list'), 'w', encoding='utf-8')

        # start when the progress presents
        WebDriverWait(self.driver, self.load_wait).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="epub-reader"]/div[3]/div/div/div'))
        )

        chapter_list = []
        done = 0
        while done < 5:
            # html = self.driver.execute_script("return document.documentElement.outerHTML;")
            epub_html = self.driver.find_element(By.XPATH, '//*[@id="epub-reader"]/div[4]/div[1]').get_attribute('outerHTML')
            soup = bs(epub_html, 'lxml')
            for chapter_soup in soup.select('div.epub-main > div'):
                chapter_name = chapter_soup.get('id', 'FALSE_CHAPTER_NAME')
                if chapter_name != 'FALSE_CHAPTER_NAME':
                    if chapter_name not in chapter_list:
                        chapter_list.append(chapter_name)
                        logging.info(f'Now last 3 chapters of {len(chapter_list)}: {chapter_list[max(-len(chapter_list),-3):]}')
                        self.parse_chapter(chapter_soup)
                        logging.info(f'Parse done! Chapter name: {chapter_name}')
                        time.sleep(self.load_wait * 0.0) # sleep little when there is new chapter
                elif chapter_soup['class'] == ['read-end']:
                    continue
                elif chapter_soup['class'] == ['scroll-loading']:
                    continue
                else:
                    print('Wrong chapter name found! Below is the full div. ')
                    print(chapter_soup)

            # scroll window height
            # # self.driver.find_element(By.XPATH, '//*[@id="app"]').send_keys(Keys.END)
            # # # Above code return: element not interactable
            self.driver.execute_script('document.getElementsByClassName("epub-single-view")[0].scrollBy(0, document.body.scrollHeight*1.2)')

            # progress | 阅读进度
            prog_elem = self.driver.find_element(By.XPATH, '//*[@id="epub-reader"]/div[3]/div/div/div').text.replace('%', '')
            logging.info(f'Read progress: {prog_elem}')

            if float(prog_elem) >= 100:
                done += 1
                # to scroll more

            # do not sleep when there is no new chapter
            time.sleep(0.0)

        self.main_html_file.write('</div>\n</body>\n')
        self.main_html_file.close()
        self.toc_html_file.close()

        return

if __name__ == '__main__':
    url = '*ePub reader link*'
    cookie_path = '*your cookie path*'
    chrome_driver_path = '*you chrome driver path*'
    a = kezhi_epub(url, cookie_path=cookie_path, chrome_exe_path=chrome_driver_path)
    a.main()