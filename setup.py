from setuptools import setup, find_packages

with open("requirements.txt", "r") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="crm_override",
    version="0.0.1",
    description="CRM Override for Frappe",
    author="Nipun",
    author_email="your.email@example.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires
)
