#!/usr/bin/env bash
# Member 2 - compile the MapReduce jobs and package them into ahd-mr.jar (run on the BigDataVM).
# Screenshot this whole terminal for the "compile and jar commands" evidence.
set -e
cd "$(dirname "$0")"

rm -rf classes && mkdir classes

# -encoding UTF-8 matters: TextUtil.java contains Arabic stop words.
javac -encoding UTF-8 -classpath "$(hadoop classpath)" -d classes src/ahd/mr/*.java

jar cvf ahd-mr.jar -C classes .
ls -l ahd-mr.jar
