package com.nantic.facturae.xmlsign;

import java.io.BufferedInputStream;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.PrintStream;
import java.net.URI;
import java.security.KeyStore;
import java.security.KeyStoreException;
import java.security.NoSuchAlgorithmException;
import java.security.PrivateKey;
import java.security.Provider;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.util.List;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;
import org.w3c.dom.Document;
import org.xml.sax.SAXException;

import es.mityc.firmaJava.libreria.utilidades.UtilidadTratarNodo;
import es.mityc.firmaJava.libreria.xades.DataToSign;
import es.mityc.javasign.EnumFormatoFirma;
import es.mityc.firmaJava.libreria.xades.FirmaXML;
import es.mityc.firmaJava.libreria.xades.XAdESSchemas;
import es.mityc.firmaJava.libreria.xades.elementos.xades.ObjectIdentifier;
import es.mityc.javasign.pkstore.CertStoreException;
import es.mityc.javasign.pkstore.IPassStoreKS;
import es.mityc.javasign.pkstore.keystore.KSStore;
import es.mityc.javasign.xml.refs.AbstractObjectToSign;
import es.mityc.javasign.xml.refs.AllXMLToSign;
import es.mityc.javasign.xml.refs.ObjectToSign;

import com.nantic.facturae.xmlsign.PassStoreKS;

public class Sign extends FirmaXML {
    public void FirmaXADES_EPES(String xmlOrigen, String xmlDestino, String policy, String certificado, String password) {
        KSStore storeManager = null;
        try {
            KeyStore ks = KeyStore.getInstance("PKCS12");
            ks.load(new FileInputStream(certificado), password.toCharArray());
            storeManager = new KSStore(ks, (IPassStoreKS)new PassStoreKS(password));
        }
        catch (KeyStoreException ex) {
            System.out.println("Error KeyStoreException...");
            System.exit(1001);
        }
        catch (NoSuchAlgorithmException ex) {
            System.out.println("Error NoSuchAlgorithmException...");
            System.exit(1002);
        }
        catch (CertificateException ex) {
            System.out.println("Error CertificateException...");
            System.exit(1003);
        }
        catch (IOException ex) {
            System.out.println("Error IOException... Provably the supplied password is incorrect");
            System.exit(1004);
        }

        List certs = null;
        try {
            certs = storeManager.getSignCertificates();
        }
        catch (CertStoreException ex) {
            System.out.println("Error al obtener los certificados");
            System.exit(1005);
        }
        if (certs == null || certs.size() == 0) {
            System.out.println("No hay certificados");
            System.exit(1006);
        }
        X509Certificate certificate = (X509Certificate)certs.get(0);
        PrivateKey privateKey = null;
        try {
            privateKey = storeManager.getPrivateKey(certificate);
        }
        catch (CertStoreException e) {
            System.out.println("Error al acceder al almac\u00e9n");
            System.exit(1007);
        }
        Provider provider = storeManager.getProvider(certificate);
        DataToSign dataToSign = this.createDataToSign(xmlOrigen, policy);
        Object[] res = null;
        try {
            res = this.signFile(certificate, dataToSign, privateKey, provider);
        }
        catch (Exception ex) {
            System.out.println("Error!!!");
            System.exit(1008);
        }
        try {
            UtilidadTratarNodo.saveDocumentToOutputStream((Document)((Document)res[0]), (OutputStream)new FileOutputStream(xmlDestino), (boolean)true);
        }
        catch (FileNotFoundException e) {
            System.out.println("Error!");
            System.exit(1009);
        }
        System.out.println("\u00a1XML de origen firmado correctamente!.");
    }

    private DataToSign createDataToSign(String xmlOrigen, String policy) {
        DataToSign dataToSign = new DataToSign();
        dataToSign.setXadesFormat(EnumFormatoFirma.XAdES_BES);
        dataToSign.setEsquema(XAdESSchemas.XAdES_132);
        dataToSign.setPolicyKey(policy);
        dataToSign.setAddPolicy(true);
        dataToSign.setXMLEncoding("UTF-8");
        dataToSign.setEnveloped(true);
        dataToSign.addObject(new ObjectToSign((AbstractObjectToSign)new AllXMLToSign(), "Documento de ejemplo", null, "text/xml", null));
        Document docToSign = this.getDocument(xmlOrigen);
        dataToSign.setDocument(docToSign);
        return dataToSign;
    }

    private Document getDocument(String resource) {
        Document doc = null;
        DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
        dbf.setNamespaceAware(true);
        try {
            doc = dbf.newDocumentBuilder().parse(new BufferedInputStream(new FileInputStream(resource)));
        }
        catch (ParserConfigurationException ex) {
            System.err.println("Error al parsear el documento");
            ex.printStackTrace();
            System.exit(-1);
        }
        catch (SAXException ex) {
            System.err.println("Error al parsear el documento");
            ex.printStackTrace();
            System.exit(-1);
        }
        catch (IOException ex) {
            System.err.println("Error al parsear el documento");
            ex.printStackTrace();
            System.exit(-1);
        }
        catch (IllegalArgumentException ex) {
            System.err.println("Error al parsear el documento");
            ex.printStackTrace();
            System.exit(-1);
        }
        return doc;
    }
}

