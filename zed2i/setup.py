from setuptools import setup

package_name = 'zed2i'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='deep',
    maintainer_email='deep@example.com',
    description='ZED2i recorder ROS2 node that writes SVO2 files.',
    license='BSD-3-Clause',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'zed2i_node = zed2i.zed2i_node:main',
        ],
    },
)
