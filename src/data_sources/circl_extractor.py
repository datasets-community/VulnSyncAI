import requests
import asyncio
from .data_source import DataSourceBase

class CirclExtractor(DataSourceBase):
    async def collect_data(self, search_params):
        vulnerabilities = []
        for param in search_params:
            print(f"Collecting CIRCL data for search parameter: {param}")
            try:
                circl_response = await self.get_circl_data(param)
                # O retorno é um dicionário com várias listas de vulnerabilidades por fonte
                for source_key, vulns in circl_response.items():
                    for vuln in vulns:
                        # Cada item é uma lista: [cve_id, vuln_data]
                        if isinstance(vuln, list) and len(vuln) == 2 and isinstance(vuln[1], dict):
                            vuln_id, vuln_data = vuln
                            vuln_data['cve_id'] = vuln_id
                            vuln_data['vendor'] = param
                            vulnerabilities.append(vuln_data)
                print(f"Found {len(vulnerabilities)} CIRCL vulnerabilities for {param}")
            except Exception as e:
                print(f"Error collecting CIRCL data for {param}: {e}")
            await asyncio.sleep(1)
        return vulnerabilities

    async def get_circl_data(self, vendor):
        # Exemplo: https://vulnerability.circl.lu/api/search/microsoft/office
        if vendor:
            url = f"https://vulnerability.circl.lu/api/search/{vendor}/{vendor}"
        else:
            url = f"https://vulnerability.circl.lu/api/search/{vendor}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()

    def normalize_data(self, vulnerability):
        # Normaliza para o formato comum do projeto
        cve_meta = vulnerability.get("cveMetadata", {})
        containers = vulnerability.get("containers", {})
        cna = containers.get("cna", {})
        descriptions = cna.get("descriptions", [])
        description = ""
        for desc in descriptions:
            if desc.get("lang") == "en":
                description = desc.get("value")
                break
        metrics = cna.get("metrics", [])
        cvss_score = None
        severity = None
        if metrics and isinstance(metrics, list):
            cvss = metrics[0].get("cvssV3_1", {})
            cvss_score = cvss.get("baseScore")
            severity = cvss.get("baseSeverity")
        return {
            "id": cve_meta.get("cveId") or vulnerability.get("cve_id"),
            "description": description,
            "published": cve_meta.get("datePublished"),
            "cvss_score": cvss_score,
            "severity": severity,
            "source": "circl"
        }