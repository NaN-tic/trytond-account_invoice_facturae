package com.nantic.facturae.xmlsign;

import java.security.cert.X509Certificate;

import es.mityc.javasign.pkstore.IPassStoreKS;

public class PassStoreKS implements IPassStoreKS {
    private transient String password;

    public PassStoreKS(String pass) {
        this.password = new String(pass);
    }

    public char[] getPassword(X509Certificate certificate, String alias) {
        return this.password.toCharArray();
    }
}

