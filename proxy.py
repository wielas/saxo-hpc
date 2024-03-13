import logging
import requests


def get_proxy_list():
    url = 'https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&protocol=http&country=DE&timeout=15000&proxy_format=ipport&format=text'
    proxy_list = []

    try:
        response = requests.get(url)
        proxy_list = response.text.split('\r\n')[:-1]
    except requests.RequestException as e:
        print('Error fetching proxy list:', e)
        # logging.critical(f"Error fetching proxy list: {e}")
    check_proxy_number(proxy_list)
    return proxy_list[:4]


def check_proxy_number(proxies):
    if len(proxies) < 4:
        logging.critical("Not enough proxies to run the scraping process")
        exit(1)


if __name__ == '__main__':
    print(get_proxy_list())
