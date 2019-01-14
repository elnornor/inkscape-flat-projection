; documentation seen at http://nsis.sourceforge.net/Docs/Chapter2.html
 
!define AppName "Inkscape Erweiterung 3D-Projeciton"
!define AppVersion "v0.1"
!define ShortName "inkscape-flat-projection"
!define Vendor "Fab Lab Region Nürnberg e.V."
!define Author "(C) 2019 Juergen Weigert <uergen@fabmail.org>"
 

Name "${AppName} ${AppVersion}"
; The OutFile instruction is required and tells NSIS where to write the installer.
; you also need at least one section.
OutFile "../out/${ShortName}-de-${AppVersion}-setup.exe"

; On Windows x64, $PROGRAMFILES and $PROGRAMFILES32 point to C:\Program Files (x86) while $PROGRAMFILES64 points to C:\Program Files. 

; The temporary directory:  $TEMP

Section "${AppName}"
 ; OutPath according to http://www.inkscapeforum.com/viewtopic.php?t=4205
 SetOutPath "$PROGRAMFILES64\inkscape\share\extensions"
 File "flat-projection.py"
 File "flat-projection.inx"
SectionEnd

