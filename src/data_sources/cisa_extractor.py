import requests
import asyncio
import time
from .data_source import DataSourceBase

class CisaExtractor(DataSourceBase):
    async def collect_data(self, search_params):
        vulnerabilities = []
        for param in search_params:
            print(f"Collecting CISA data for search parameter: {param}")
            time.sleep(5)
            try:
                cisa_response = await self.get_cisa_data(param)
                if cisa_response and 'vulnerabilities' in cisa_response:
                    for vuln in cisa_response['vulnerabilities']:
                        vuln['vendor'] = param  # Add vendor based on search parameter
                        vulnerabilities.append(vuln)
                    print(f"Found {len(cisa_response['vulnerabilities'])} CISA vulnerabilities for {param}")
                else:
                    print(f"No vulnerabilities found for {param}")
            except Exception as e:
                print(f"Error collecting data for {param}: {e}")
        return vulnerabilities

    async def get_cisa_data(self, keyword):
        base_url = 'https://kevin.gtfkd.com/kev'
        params = {'key': keyword}
        headers = {'User-Agent': 'Mozilla/5.0'}
        await asyncio.sleep(5)
        response = requests.get(base_url, params=params, headers=headers)
        if response.status_code == 403:
            print(f"Rate limit exceeded or access forbidden for keyword: {keyword}")
            await asyncio.sleep(5)
            response = requests.get(base_url, params=params, headers=headers)
            print(f"CISA API response status code after retry: {response.status_code}")
        response.raise_for_status()
        return response.json()

    def normalize_data(self, vulnerability):
        # Use new field names from the updated API
        nvd_data = vulnerability.get('nvdData', [{}])[0] if vulnerability.get('nvdData') else {}
        return {
            'id': vulnerability.get('cveID'),
            'description': vulnerability.get('shortDescription', ''),
            'published': vulnerability.get('dateAdded'),
            'cvss_score': nvd_data.get('baseScore'),
            'severity': nvd_data.get('baseSeverity'),
            'source': 'cisa',
        }