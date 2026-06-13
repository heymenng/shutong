from setuptools import setup, find_packages

setup(
    name="书童程序",
    version="1.0.0",
    description="伴读书童AI - 儿童陪伴智能体",
    packages=find_packages(),
    install_requires=[
        "requests",
        "pyttsx3",
        "numpy",
        "scikit-learn",
    ],
    entry_points={
        "console_scripts": [
            "书童=书童程序.主程序:main",
        ],
    },
    python_requires=">=3.8",
)
