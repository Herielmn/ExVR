const RT_ICON: u16 = 3;
const RT_GROUP_ICON: u16 = 14;
const GROUP_ID: u16 = 1;
const LANGUAGE: u16 = 0x0409;
const ICON_FLAGS: u16 = 0x1010;
const GROUP_FLAGS: u16 = 0x1030;

struct Image {
    width: u8,
    height: u8,
    colors: u8,
    planes: u16,
    bits: u16,
    offset: usize,
    length: usize,
}

fn word(data: &[u8], at: usize) -> u16 {
    u16::from_le_bytes([data[at], data[at + 1]])
}

fn long(data: &[u8], at: usize) -> u32 {
    u32::from_le_bytes([data[at], data[at + 1], data[at + 2], data[at + 3]])
}

fn images(ico: &[u8]) -> Vec<Image> {
    assert_eq!(word(ico, 2), 1, "logo.ico is not an icon file");
    (0..word(ico, 4) as usize)
        .map(|index| {
            let at = 6 + index * 16;
            Image {
                width: ico[at],
                height: ico[at + 1],
                colors: ico[at + 2],
                planes: word(ico, at + 4),
                bits: word(ico, at + 6),
                length: long(ico, at + 8) as usize,
                offset: long(ico, at + 12) as usize,
            }
        })
        .collect()
}

fn header(out: &mut Vec<u8>, length: usize, kind: u16, name: u16, flags: u16, language: u16) {
    out.extend_from_slice(&(length as u32).to_le_bytes());
    out.extend_from_slice(&32u32.to_le_bytes());
    out.extend_from_slice(&0xFFFFu16.to_le_bytes());
    out.extend_from_slice(&kind.to_le_bytes());
    out.extend_from_slice(&0xFFFFu16.to_le_bytes());
    out.extend_from_slice(&name.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&flags.to_le_bytes());
    out.extend_from_slice(&language.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
}

fn align(out: &mut Vec<u8>) {
    while out.len() % 4 != 0 {
        out.push(0);
    }
}

fn resource_file(ico: &[u8], images: &[Image]) -> Vec<u8> {
    let mut out = Vec::new();
    header(&mut out, 0, 0, 0, 0, 0);
    for (index, image) in images.iter().enumerate() {
        header(
            &mut out,
            image.length,
            RT_ICON,
            index as u16 + 1,
            ICON_FLAGS,
            LANGUAGE,
        );
        out.extend_from_slice(&ico[image.offset..image.offset + image.length]);
        align(&mut out);
    }

    let mut group = Vec::new();
    group.extend_from_slice(&0u16.to_le_bytes());
    group.extend_from_slice(&1u16.to_le_bytes());
    group.extend_from_slice(&(images.len() as u16).to_le_bytes());
    for (index, image) in images.iter().enumerate() {
        group.push(image.width);
        group.push(image.height);
        group.push(image.colors);
        group.push(0);
        group.extend_from_slice(&image.planes.to_le_bytes());
        group.extend_from_slice(&image.bits.to_le_bytes());
        group.extend_from_slice(&(image.length as u32).to_le_bytes());
        group.extend_from_slice(&(index as u16 + 1).to_le_bytes());
    }
    header(
        &mut out,
        group.len(),
        RT_GROUP_ICON,
        GROUP_ID,
        GROUP_FLAGS,
        LANGUAGE,
    );
    out.extend_from_slice(&group);
    align(&mut out);
    out
}

fn largest_bitmap(images: &[Image]) -> &Image {
    images
        .iter()
        .filter(|image| image.bits == 32 && image.width > 0 && image.width <= 64)
        .max_by_key(|image| image.width)
        .expect("logo.ico has no 32-bit image of 64 px or less")
}

fn rgba(ico: &[u8], image: &Image) -> Vec<u8> {
    let at = image.offset;
    assert_eq!(long(ico, at), 40, "expected a BITMAPINFOHEADER in logo.ico");
    assert_eq!(word(ico, at + 14), 32, "expected 32 bits per pixel");
    let side = long(ico, at + 4) as usize;
    let pixels = at + 40;
    let mut out = vec![0u8; side * side * 4];
    for y in 0..side {
        for x in 0..side {
            let from = pixels + ((side - 1 - y) * side + x) * 4;
            let to = (y * side + x) * 4;
            out[to] = ico[from + 2];
            out[to + 1] = ico[from + 1];
            out[to + 2] = ico[from];
            out[to + 3] = ico[from + 3];
        }
    }
    out
}

fn main() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
    let out = std::path::PathBuf::from(std::env::var_os("OUT_DIR").expect("OUT_DIR is unset"));

    let logo = root.join("..").join("logo").join("logo.ico");
    println!("cargo:rerun-if-changed={}", logo.display());
    let ico = std::fs::read(&logo).expect("logo/logo.ico is missing");
    let images = images(&ico);

    let source = largest_bitmap(&images);
    std::fs::write(out.join("icon.rgba"), rgba(&ico, source)).expect("could not write icon.rgba");
    std::fs::write(
        out.join("icon.side"),
        format!("{}", long(&ico, source.offset + 4)),
    )
    .expect("could not write icon.side");

    let resources = out.join("icon.res");
    std::fs::write(&resources, resource_file(&ico, &images)).expect("could not write icon.res");

    let manifest = root.join("exvr-host.manifest");
    println!("cargo:rerun-if-changed=exvr-host.manifest");
    if std::env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("msvc") {
        println!("cargo:rustc-link-arg-bins=/MANIFEST:EMBED");
        println!(
            "cargo:rustc-link-arg-bins=/MANIFESTINPUT:{}",
            manifest.display()
        );
        println!("cargo:rustc-link-arg-bins=/MANIFESTUAC:NO");
        println!("cargo:rustc-link-arg-bins={}", resources.display());
    }
}
