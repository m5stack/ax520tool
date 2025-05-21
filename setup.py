from setuptools import setup, find_packages

setup(
    name='ax520tool',
    version='1.0.0',
    packages=find_packages(),
    install_requires=[
        'pyserial',
        'tqdm'
    ],
    author='Xiao Han',
    author_email='hansh-sz@hotmail.com',
    description='Fully pythonic flash programmer tool for Axera AX520',
    long_description=open('README.md').read(),  
    long_description_content_type='text/markdown',
    url='https://github.com/m5stack/ax520tool',  
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',  
    entry_points={
        'console_scripts': [
            'ax520tool=ax520tool.cli:main', 
        ],
    },
)
