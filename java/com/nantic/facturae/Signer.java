package com.nantic.facturae;

import com.nantic.facturae.xmlsign.Sign;

public class Signer {

    public static void main (String [] args) {
        if (args.length < 1) {
            System.out.println("Missing operation param");
            System.exit(-1);
        }
        int op = Integer.parseInt(args[0]);
        switch (op) {
            case 0: {
                if (args.length < 6) {
                    System.out.println("Missing expected params: 0 " +
                        "<file-to-sign.xml> <target-file.xsig> <policy> " +
                        "<PKCS12-certificate.p12> <password>");
                    System.exit(-1);
                }
                Sign s = new Sign();
                s.FirmaXADES_EPES(args[1], args[2], args[3], args[4], args[5]);
                break;
            }
            // case 1: {
            //     Verify v = new Verify();
            //     if (v.validarFichero(args[1])) break;
            //     System.out.println("La firma no es valida.");
            //     System.exit(2001);
            //     break;
            // }
            // case 2: {
            //     PDFSign pdfsign = new PDFSign();
            //     float[] dim = new float[]{Float.parseFloat(args[8]), Float.parseFloat(args[9]), Float.parseFloat(args[10]), Float.parseFloat(args[11])};
            //     try {
            //         pdfsign.FirmaPDF(args[1], args[2], args[3], args[4], args[5], args[6], args[7], dim[0], dim[1], dim[2], dim[3]);
            //     }
            //     catch (Exception e) {
            //         e.printStackTrace();
            //         System.exit(3001);
            //     }
            //     break;
            // }
            default: {
                System.out.println("Unexpected operation");
                System.exit(9001);
            }
        }
        System.exit(0);
    }
}
