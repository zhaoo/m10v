#include "m10v_aspect_config.h"
.syntax unified
.arm
.fpu vfpv3
.text
.macro entry name
.global m10v_aspect_\name
.type m10v_aspect_\name,%function
m10v_aspect_\name:
.endm
.macro jump address
    ldr pc, =\address
.endm

entry label
#if M10V_HALF_FRAME
    cmp r1,#6
    beq m10v_aspect_half_id
#endif
    cmp r1,#5
    beq m10v_aspect_id
    cmp r1,#1
    jump 0x540b942c
entry resolution_hook
#if M10V_HALF_FRAME
    cmp r2,#6
    bne 8f
    ldr ip,[sp]
    mov r2,r3
    mov r3,ip
    vmov r0,s0
    b m10v_aspect_half_resolution
8:
#endif
    cmp r2,#5
    bne 1f
    ldr ip,[sp]
    mov r2,r3
    mov r3,ip
    vmov r0,s0
    b m10v_aspect_resolution
1:  cmp r2,#4
    jump 0x540b9454
entry capture_identity
#if M10V_HALF_FRAME
    cmp r9,#6
    bne 8f
    mov r3,#6
    strb r3,[r7,#0x9fe]
    jump 0x534525e4
8:
#endif
    cmp r9,#5
    bne 1f
    mov r3,#5
    strb r3,[r7,#0x9fe]
    jump 0x534525e4
1:  cmp r9,#4
    jump 0x540b9578
entry binary_class
    uxtb r0,r0
    cmp r0,#5
#if M10V_HALF_FRAME
    cmpne r0,#6
#endif
    moveq r0,#0
    bxeq lr
    jump 0x540b978c
entry write
    ldr ip,[r0,#0x20]
    ldrb ip,[ip,#0xf2]
    cmp ip,#5
#if M10V_HALF_FRAME
    cmpne ip,#6
#endif
    bne 1f
    mov r0,r1
    mov r1,#0
    mov r2,ip
    jump 0x535d02b4
1:  ldr ip,[r0,#0x20]
    jump 0x540b9774
entry extract
    push {r0,r1,r4,lr}
    mov r0,r1
    mov r1,#0
    bl native_ifd_byte
    cmp r0,#5
#if M10V_HALF_FRAME
    cmpne r0,#6
#endif
    mov ip,r0
    pop {r0,r1,r4,lr}
    bne 1f
    ldr r0,[r0,#0xc]
    strb ip,[r0,#0x7b6]
    bx lr
1:  cmp ip,#4
    beq old_extract65
    mov ip,sp
    jump 0x535ed43c
entry merge
    push {r4,r5,r6,lr}
    mov r4,r1
    ldrb r5,[r1,#0x4c2]
    bl old_native_merge
    cmp r5,#1
    cmpne r5,#4
    cmpne r5,#5
#if M10V_HALF_FRAME
    cmpne r5,#6
#endif
    strbeq r5,[r4,#0x4c2]
    pop {r4,r5,r6,pc}
entry ubox
    cmp r1,#1
    blo old_native_ubox
    cmp r1,#6
    bhi old_native_ubox
    push {r4,r5,r6,lr}
    ldr r4,[r0,#4]
    ldrb r5,[r4,#0x4c2]
    add r6,r0,#8
    ldr r4,[r6,r1,lsl#2]
    bl old_native_ubox
    cmp r5,#1
    cmpne r5,#4
    cmpne r5,#5
#if M10V_HALF_FRAME
    cmpne r5,#6
#endif
    strbeq r5,[r4,#0x4c2]
    pop {r4,r5,r6,pc}
entry shading
    ldr ip,[sp,#8]
    cmp ip,#0
    beq old_native_shading
    ldrb ip,[ip,#0xf2]
    cmp ip,#5
#if M10V_HALF_FRAME
    cmpne ip,#6
#endif
    beq old_shading65
    ldr ip,[sp,#8]
    jump 0x540b94c8
entry screen_origin
#if M10V_HALF_FRAME
    cmp r1,#6
    bne 8f
    mov ip,#181
    strh ip,[r2]
    mov ip,#0
    strh ip,[r3]
    bx lr
8:
#endif
    cmp r1,#5
    bne 1f
    mov ip,#80
    strh ip,[r2]
    mov ip,#0
    strh ip,[r3]
    bx lr
1:  cmp r1,#4
    jump 0x540b94ec
entry thumb_origin
#if M10V_HALF_FRAME
    cmp r1,#6
    bne 8f
    mov ip,#23
    strh ip,[r2]
    mov ip,#0
    strh ip,[r3]
    bx lr
8:
#endif
    cmp r1,#5
    bne 1f
    mov ip,#10
    strh ip,[r2]
    mov ip,#0
    strh ip,[r3]
    bx lr
1:  cmp r1,#4
    jump 0x540b9510
entry filter_hook
#if M10V_HALF_FRAME
    cmp r0,#6
    bne 8f
    push {r0,r1,r2,r3,ip,lr}
    ldr r0,[r5,#0x7b8]
    mov r1,r7
    bl m10v_aspect_half_filter
    vmov s15,r0
    pop {r0,r1,r2,r3,ip,lr}
    jump 0x535030e0
8:
#endif
    cmp r0,#5
    bne 1f
    push {r0,r1,r2,r3,ip,lr}
    ldr r0,[r5,#0x7b8]
    mov r1,r7
    bl m10v_aspect_filter
    vmov s15,r0
    pop {r0,r1,r2,r3,ip,lr}
    jump 0x535030e0
1:  cmp r0,#4
    jump 0x540b8cb0
entry live_width_hook
    ldrb ip,[sp]
    cmp ip,#4
    cmpne ip,#5
#if M10V_HALF_FRAME
    cmpne ip,#6
#endif
    beq m10v_aspect_live_width
    jump 0x540b85bc
entry live_height_hook
    ldrb ip,[sp]
    cmp ip,#4
    cmpne ip,#5
#if M10V_HALF_FRAME
    cmpne ip,#6
#endif
    beq m10v_aspect_live_height
    jump 0x540b860c
entry face_config
#if M10V_HALF_FRAME
    cmp r3,#6
    moveq r3,#0
#endif
    cmp r3,#5
    moveq r3,#0
    cmp r3,#4
    jump 0x540b9144
entry live_select
    cmp r2,#4
    cmpne r2,#5
#if M10V_HALF_FRAME
    cmpne r2,#6
#endif
    bne 1f
    cmp r1,#1
    bhi 1f
    b m10v_aspect_live_region
1:  cmp r2,#4
    jump 0x540b916c
entry common_dispatch
    push {r0,r1,r2,r3,r4,r5,ip,lr}
    cmp r1,#1
    bhi 1f
    bl m10v_aspect_current
    cmp r0,#4
    cmpne r0,#5
#if M10V_HALF_FRAME
    cmpne r0,#6
#endif
    bne 1f
    str r0,[sp,#8]
    pop {r0,r1,r2,r3,r4,r5,ip,lr}
    mov r3,r4
    bl m10v_aspect_live_region
    sub sp,fp,#0x1c
    ldm sp,{r3,r4,r5,r6,fp,sp,lr}
    bx lr
1:  pop {r0,r1,r2,r3,r4,r5,ip,lr}
    cmp r5,#4
    jump 0x540b92d4

/* The extra caption is intercepted before the unchanged native/film routes. */
entry text_prepare
    push {r0,r1,r2,r3,ip,lr}
    mrs r3,apsr
    push {r3,r4}
    mov r0,r7
    ldr r1,[sp,#8]
    bl m10v_aspect_caption_for
    cmp r0,#0
    beq 1f
    str r0,[sp,#24]
    pop {r3,r4}
    msr apsr_nzcvq,r3
    pop {r0,r1,r2,r3,ip,lr}
    mov r9,r0
    sub r8,fp,#0xb0
    mov r0,r8
    mov r7,ip
    movw ip,#:lower16:m10v_aspect_id_record
    movt ip,#:upper16:m10v_aspect_id_record
    ldr r3,[ip,#8]
    jump 0x53396700
1:  pop {r3,r4}
    msr apsr_nzcvq,r3
    pop {r0,r1,r2,r3,ip,lr}
    push {ip,lr}
    jump 0x540b89fc
entry text_draw
    push {r0,r1,r2,r3,ip,lr}
    mrs r3,apsr
    push {r3,r4}
    mov r0,r7
    ldr r1,[sp,#8]
    bl m10v_aspect_caption_for
    cmp r0,#0
    beq 1f
    str r0,[sp,#24]
    pop {r3,r4}
    msr apsr_nzcvq,r3
    pop {r0,r1,r2,r3,ip,lr}
    mov r3,ip
    jump 0x5339710c
1:  pop {r3,r4}
    msr apsr_nzcvq,r3
    pop {r0,r1,r2,r3,ip,lr}
    push {ip,lr}
    jump 0x540b8bc8

entry af_bounds_branch
#if M10V_HALF_FRAME
    cmp r0,#6
    beq af_bounds_private
#endif
    cmp r0,#5
    beq af_bounds_private
    cmp r0,#1
    jump 0x540b66a4
entry af_size_branch
#if M10V_HALF_FRAME
    cmp r0,#6
    beq af_size_private
#endif
    cmp r0,#5
    beq af_size_private
    cmp r0,#1
    jump 0x540b66e8
entry af_small_branch
#if M10V_HALF_FRAME
    cmp r0,#6
    beq af_small_private
#endif
    cmp r0,#5
    beq af_small_private
    cmp r0,#1
    jump 0x540b6730

.section .rodata,"a",%progbits
.align 2
.global m10v_aspect_caption
m10v_aspect_caption:
    .byte 4,1,0,0
    .word m10v_aspect_caption+8
    .hword 54,120,55,0

#if M10V_HALF_FRAME
.align 2
.global m10v_aspect_half_caption
m10v_aspect_half_caption:
    .byte 9,1,0,0
    .word m10v_aspect_half_caption+8
    .hword 72,97,108,102,32,51,58,52,0
#endif
