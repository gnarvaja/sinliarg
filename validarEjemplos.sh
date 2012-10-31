#!/bin/bash

trang sinliarg.rnc sinliarg.rng
for x in ejemplos/*; do
	./validar.py sinliarg.rng $x;
done
