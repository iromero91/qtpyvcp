===========================
Install from apt repository
===========================



This only works for amd64.



Upgrade the system


.. code:: sh

	$ sudo apt update
	$ sudo apt upgrade


Add kcjengr repository to debian 12


.. code:: sh

	$ echo 'deb [arch=amd64] https://repository.qtpyvcp.com/apt develop main' | sudo tee /etc/apt/sources.list.d/kcjengr.list


Get the apt keys


.. code:: sh

    $ sudo apt install curl
	$ curl -sS https://repository.qtpyvcp.com/repo/kcjengr.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/kcjengr.gpg
	$ gpg --keyserver keys.openpgp.org --recv-key 2DEC041F290DF85A


Update the repositories


.. code:: sh

	$ sudo apt update


Install qtpyvcp


.. code:: sh

	$ sudo apt install python3-qtpyvcp


Install some vcps, for now there are 3 in the repository

Probe Basic
Monokrom
Turbonc

to install them just run


.. code:: sh
	
	$ sudo apt install python3-probe-basic
	$ sudo apt install python3-monokrom
	$ sudo apt install python3-turbonc


