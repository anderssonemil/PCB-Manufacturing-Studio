import de.thomas_oster.liblasercut.*;
import de.thomas_oster.liblasercut.drivers.EpilogHelix;
import de.thomas_oster.liblasercut.properties.PowerSpeedFocusFrequencyProperty;
import java.nio.file.*;import java.io.*;import java.util.*;
/** Offline only: consumes already quantized, bed-checked integer coordinates. */
public class PCBHelixJob {
 public static void main(String[] args)throws Exception {
  List<String> lines=Files.readAllLines(Path.of(args[0]));String[] h=lines.get(0).split("\t");
  int dpi=Integer.parseInt(h[0]),speed=Integer.parseInt(h[1]),power=Integer.parseInt(h[2]),frequency=Integer.parseInt(h[3]);
  PowerSpeedFocusFrequencyProperty p=new PowerSpeedFocusFrequencyProperty(true);p.setSpeed(speed);p.setPower(power);p.setFrequency(frequency);p.setFocus(0);
  LaserJob j=new LaserJob(h[6],h[6],"PCB_ISOLATOR");j.setAutoFocusEnabled(false);
  VectorPart v=new VectorPart(p,dpi);
  for(int i=1;i<lines.size();i++){String[] coords=lines.get(i).split(" ");boolean first=true;for(String xy:coords){String[] c=xy.split(",");int x=Integer.parseInt(c[0]),y=Integer.parseInt(c[1]);if(first)v.moveto(x,y);else v.lineto(x,y);first=false;}}
  j.addPart(v);EpilogHelix cutter=new EpilogHelix("offline");cutter.setBedWidth(Double.parseDouble(h[4]));cutter.setBedHeight(Double.parseDouble(h[5]));cutter.setAutoFocus(false);cutter.setHideSoftwareFocus(true);
  try(OutputStream out=Files.newOutputStream(Path.of(args[1]))){cutter.saveJob(out,j);}
 }
}
