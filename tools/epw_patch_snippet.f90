! -----------------------------------------------------------------------------
! EPW patch snippet (interface-aligned draft): Normal / Umklapp split for EPW
!
! Source alignment from QE/EPW mainline (QEF/q-e):
! - main q-loop entry: selfen_elec_q(iqq, iq, totq, first_cycle) in EPW/src/selfen.f90
! - call site: use_wannier.f90 calls selfen_elec_q when elecselfen/specfun_el is enabled
! - k+q mapping/folding primitives: kfold.f90 (backtoBZ/ktokpmq) and bzgrid.f90 (kpmq_map)
!
! This snippet is a drop-in template for your local EPW tree. It keeps your output
! file contract used by tools/qe_epw_pack.py:
!   epw_friction_tensors.dat
!   # atom_id  LambdaN(9 row-major)  LambdaU(9 row-major)
!
! NOTE:
! - Replace projector_from_mode(...) with your atom/mode projection formula.
! - Keep units consistent with your selected self-energy/transport branch.
! -----------------------------------------------------------------------------

module epw_nu_export
  use kinds,        only : dp
  use ep_constants, only : eps5
  use kfold,        only : backtoBZ
  implicit none
contains

  subroutine classify_kq_nu(xk_crys, xq_crys, nk1, nk2, nk3, is_umklapp, g0)
    implicit none
    real(dp), intent(in)  :: xk_crys(3), xq_crys(3)
    integer,  intent(in)  :: nk1, nk2, nk3
    logical,  intent(out) :: is_umklapp
    integer,  intent(out) :: g0(3)
    real(dp) :: xx, yy, zz
    real(dp) :: xkq(3)

    xkq = xk_crys + xq_crys

    xx = xkq(1) * real(nk1, dp)
    yy = xkq(2) * real(nk2, dp)
    zz = xkq(3) * real(nk3, dp)

    call backtoBZ(xx, yy, zz, nk1, nk2, nk3)

    g0(1) = nint(xkq(1) * real(nk1, dp) - xx)
    g0(2) = nint(xkq(2) * real(nk2, dp) - yy)
    g0(3) = nint(xkq(3) * real(nk3, dp) - zz)

    is_umklapp = (abs(g0(1)) > 0) .or. (abs(g0(2)) > 0) .or. (abs(g0(3)) > 0)
  end subroutine classify_kq_nu

  subroutine dump_friction_tensors(fname, nat, lambda_n, lambda_u)
    implicit none
    character(len=*), intent(in) :: fname
    integer,          intent(in) :: nat
    real(dp),         intent(in) :: lambda_n(nat,3,3), lambda_u(nat,3,3)
    integer :: iat, iu

    iu = 99
    open(unit=iu, file=trim(fname), status='replace', action='write')
    write(iu,'(A)') '# atom_id  LambdaN(9 row-major)  LambdaU(9 row-major)'
    do iat = 1, nat
      write(iu,'(I8,1X,18(ES22.14,1X))') iat, &
        lambda_n(iat,1,1), lambda_n(iat,1,2), lambda_n(iat,1,3), &
        lambda_n(iat,2,1), lambda_n(iat,2,2), lambda_n(iat,2,3), &
        lambda_n(iat,3,1), lambda_n(iat,3,2), lambda_n(iat,3,3), &
        lambda_u(iat,1,1), lambda_u(iat,1,2), lambda_u(iat,1,3), &
        lambda_u(iat,2,1), lambda_u(iat,2,2), lambda_u(iat,2,3), &
        lambda_u(iat,3,1), lambda_u(iat,3,2), lambda_u(iat,3,3)
    enddo
    close(iu)
  end subroutine dump_friction_tensors

end module epw_nu_export

! -----------------------------------------------------------------------------
! Suggested integration block inside selfen_elec_q (or transport branch):
!
!   use epw_nu_export, only : classify_kq_nu, dump_friction_tensors
!   use input,         only : nkf1, nkf2, nkf3
!   use global_var,    only : xkf, xqf, nbndfst
!
!   real(dp), allocatable :: lambda_n(:, :, :), lambda_u(:, :, :)
!   logical :: is_u
!   integer :: g0(3), iat, imode, ibnd, jbnd, ik, ikk, ikq
!   real(dp) :: contrib, proj
!
!   allocate(lambda_n(nat,3,3), lambda_u(nat,3,3))
!   lambda_n = 0.0_dp
!   lambda_u = 0.0_dp
!
!   do ik = 1, nktotf
!     ikk = 2 * ik - 1
!     ikq = ikk + 1
!     call classify_kq_nu(xkf(:, ikk), xqf(:, iq), nkf1, nkf2, nkf3, is_u, g0)
!
!     do imode = 1, nmodes
!       do ibnd = 1, nbndfst
!         do jbnd = 1, nbndfst
!           ! Keep same contrib definition as your branch (selfen/transport):
!           ! contrib = |g|^2 * occupation/broadening weights * wkf/wqf factors
!           contrib = g2_contrib(ibnd, jbnd, imode, ik)
!
!           do iat = 1, nat
!             ! Replace by your atom/mode projection (e.g., eigenvector-resolved weight)
!             proj = projector_from_mode(iat, imode)
!             if (is_u) then
!               lambda_u(iat,1,1) = lambda_u(iat,1,1) + contrib * proj
!             else
!               lambda_n(iat,1,1) = lambda_n(iat,1,1) + contrib * proj
!             endif
!           enddo
!
!         enddo
!       enddo
!     enddo
!   enddo
!
!   call dump_friction_tensors('epw_friction_tensors.dat', nat, lambda_n, lambda_u)
! -----------------------------------------------------------------------------
