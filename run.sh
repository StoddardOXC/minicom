#!/bin/sh

PREFIX=${HOME}/projects/prefix
LIBPREFIX=${PREFIX}/lib
BINPREFIX=${PREFIX}/bin

PYTHONVER=`python3 -c 'import sys; v=sys.version_info; print(".".join(map(str, (v.major, v.minor))))'`

export LD_LIBRARY_PATH=${LIBPREFIX}
export PYSDL2_DLL_PATH=${LIBPREFIX}
export PYTHONPATH=${LIBPREFIX}/python${PYTHONVER}/site-packages

if ! echo $PATH | fgrep -q ${BINPREFIX}
then
	export PATH=${PATH}:${BINPREFIX}
fi

"$@"
