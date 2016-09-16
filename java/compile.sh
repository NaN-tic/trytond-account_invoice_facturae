#!/bin/bash

GENERATED_JAR="nantic-facturae-0.1.jar"

rm lib/$GENERATED_JAR

if [ -z "$JAVA_HOME" ]; then
    directories="/usr/lib/jvm/java-7-openjdk-amd64/bin /usr/lib/j2sdk1.6-sun /usr/lib/j2sdk1.5-sun"
    for d in $directories; do
        if [ -d "$d" ]; then
            export JAVA_HOME="$d"
        fi
    done
fi

# echo "JAVA_HOME=$JAVA_HOME"
# export PATH="$JAVA_HOME"/bin:/bin:/usr/bin
export CLASSPATH=$(ls -1 lib/* | grep jar$ | awk '{printf "%s:", $1}')

# echo "Class-Path: $(ls -1 lib/* | grep jar$ | awk '{printf "%s:", $1}')" > Manifest.txt

FILES=$(find com -iname "*.java")

echo "Compiling com.nantic.facturae"
javac -Xlint:deprecation $FILES || exit

# echo "Main-Class: com.nantic.facturae.Signer" > Manifest.txt
# echo "Class-Path:" >> Manifest.txt
# for jarfile in `ls -1 lib/*.jar`
# do
#     echo "  $jarfile" >> Manifest.txt
# done
# echo "" >> Manifest.txt
#
# jar cvfm nantic-facturae-0.1.jar Manifest.txt com
jar cvf $GENERATED_JAR com
mv $GENERATED_JAR lib/$GENERATED_JAR

# echo "Executing java com.nantic.facturae.Sign"
export CLASSPATH="lib/$GENERATED_JAR"":$CLASSPATH"
java com.nantic.facturae.Signer
