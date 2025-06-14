from setuptools import setup, find_packages

setup(
    name="ai-promoter",
    version="0.1.0",
    description="A Flask web application for automating social media promotion",
    author="Snyk Labs",
    author_email="labs@snyk.io",
    url="https://github.com/snyk-labs/ai-promoter",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "flask>=2.0.0",
        "flask-login>=0.6.0",
        "flask-sqlalchemy>=3.0.0",
        "flask-migrate>=4.0.0",
        "sqlalchemy>=2.0.0",
        "google-generativeai>=0.3.0",
        "python-jose>=3.3.0",
        "requests>=2.28.0",
        "feedparser>=6.0.0",
        "click>=8.0.0",
        "gunicorn>=21.2.0",
        "python-dotenv>=1.0.0",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.11",
)
