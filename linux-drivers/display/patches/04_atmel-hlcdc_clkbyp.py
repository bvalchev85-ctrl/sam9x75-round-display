import io
p="/home/attila/sam9x75-rdk/buildroot/output/build/linux-custom/drivers/gpu/drm/atmel-hlcdc/atmel_hlcdc_crtc.c"
s=open(p).read()
old="\t\tif (div < 2) {\n\t\t\tdiv = 2;\n\t\t} else if ("
new=("\t\tif (div < 2) {\n"
     "\t\t\t/* sam9x75 RDK: sys_clk == pixel clock -> bypass divider so the\n"
     "\t\t\t * DSI gets the exact mode clock (else pixel = sys_clk/2). */\n"
     "\t\t\tif (crtc->dc->desc->is_xlcdc) {\n"
     "\t\t\t\tcfg |= ATMEL_XLCDC_CLKBYP;\n"
     "\t\t\t\tmask |= ATMEL_XLCDC_CLKBYP;\n"
     "\t\t\t}\n"
     "\t\t\tdiv = 2;\n"
     "\t\t} else if (")
n=s.count(old)
if n!=1:
    print("MATCH COUNT",n,"- ABORT (not exactly 1)"); raise SystemExit(1)
open(p,"w").write(s.replace(old,new))
print("PATCHED ok")
