#!/bin/bash
set -e

cd `dirname $0`

sbuild --chroot-mode=unshare --no-clean-source

