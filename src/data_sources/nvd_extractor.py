import requests
import asyncio
import time
from .data_source import DataSourceBase

class NvdExtractor(DataSourceBase):
    async def collect_data(self, search_params):
        vulnerabilities = []
        for param in search_params:
            print(f"Collecting NVD data for search parameter: {param}")
            time.sleep(5)
            try:
                nvd_response = await self.get_nvd_data(param)
                if nvd_response and 'vulnerabilities' in nvd_response:
                    for vuln in nvd_response['vulnerabilities']:
                        vuln['vendor'] = param  # Add vendor based on search parameter
                        vulnerabilities.append(vuln)
                    print(f"Found {len(nvd_response['vulnerabilities'])} NVD vulnerabilities for {param}")
                else:
                    print(f"No vulnerabilities found for {param}")
            except Exception as e:
                print(f"Error collecting data for {param}: {e}")
        return vulnerabilities

    async def get_nvd_data(self, keyword):
        base_url = 'https://services.nvd.nist.gov/rest/json/cves/2.0'
        params = {'keywordSearch': keyword}
        headers = {'User-Agent': 'Mozilla/5.0'}
        await asyncio.sleep(5)
        response = requests.get(base_url, params=params, headers=headers)
        if response.status_code == 403:
            print(f"Rate limit exceeded or access forbidden for keyword: {keyword}")
            await asyncio.sleep(5)
            response = requests.get(base_url, params=params, headers=headers)
            print(f"NVD API response status code after retry: {response.status_code}")
        response.raise_for_status()
        return response.json()

    def normalize_data(self, vulnerability):
        cve = vulnerability.get('cve', {}) if isinstance(vulnerability, dict) else {}
        if not isinstance(cve, dict):
            cve = {}

        # Descrição em inglês
        descriptions = cve.get('descriptions', []) if isinstance(cve, dict) else []
        description = ''
        if isinstance(descriptions, list):
            for desc in descriptions:
                if isinstance(desc, dict) and desc.get('lang') == 'en':
                    description = desc.get('value', '')
                    break

        # CVSS v3.1 (pega o mais relevante, geralmente o último ou o de source 'nvd@nist.gov')
        metrics = cve.get('metrics', {}) if isinstance(cve, dict) else {}
        cvss_score = ''
        severity = ''
        if isinstance(metrics, dict):
            cvss_v31 = metrics.get('cvssMetricV31', [])
            if isinstance(cvss_v31, list) and cvss_v31:
                # Preferencialmente pega o que tem source 'nvd@nist.gov'
                cvss_data = None
                for metric in cvss_v31:
                    if isinstance(metric, dict) and metric.get('source') == 'nvd@nist.gov':
                        cvss_data = metric.get('cvssData', {})
                        break
                if not cvss_data:
                    cvss_data = cvss_v31[-1].get('cvssData', {}) if isinstance(cvss_v31[-1], dict) else {}
                if isinstance(cvss_data, dict):
                    cvss_score = cvss_data.get('baseScore', '')
                    severity = cvss_data.get('baseSeverity', '')

        return {
            'id': cve.get('id', '') if isinstance(cve, dict) else '',
            'description': description,
            'published': cve.get('published', '') if isinstance(cve, dict) else '',
            'cvss_score': cvss_score,
            'severity': severity,
            'source': 'nvd'
        }