## Processes dbpedia n-gram (nq and nt) files: strips the protocol and site
## part of all uris, and prints the file in a tab separated format.
BEGIN {
  FS = "> <"
}
{
  for (i = 1; i <= NF; i++) {
    sub(/.+\//, "", $((i)))
  }
  sub(/>.*/, "", $((NF)))
  for (i = 1; i < NF; i++) {
    printf("%s\t", $((i)))
  }
  print $((NF))
}
